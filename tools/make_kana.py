"""Redraws the kana in the Kkomi pen and adds the half-width katakana.

    make_kana.py SOURCE.otf BASE.ttf OUT.ttf

The original Kkomi font draws its Hangul and Latin with a round pen but fills its kana
(and symbols such as the stars) with a plain gothic. This script traces the centerlines
of those gothic kana, sorts them into strokes in standard stroke order, and draws every
stroke again with the round pen measured from the Kkomi Hangul: straight strokes with a
slight bow, turns rounded to a radius of 40, round ends, no hooks. A few kana get their
strokes laid out by hand where the gothic shape and the handwritten stroke order differ.
The small kana are the large ones scaled down, and ゕ ゖ (missing from the original) are
made the same way. The half-width katakana U+FF61-FF9F use the same centerlines narrowed
into the half cell. The stars are drawn again with the same pen.

It runs on the light base font (make_mono_static.py), before the weights are made.
"""
import sys, math, zlib, numpy as np, pathops
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage
from skimage.morphology import skeletonize
from skan import Skeleton
from fontTools.ttLib import TTFont
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.cu2quPen import Cu2QuPen
ORIG, MONO, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
# The base is light: the Regular weight adds 12 to upright and 9 to flat strokes, so a
# 58 pen here comes out at 70 and 67 there, like the Hangul strokes.
PEN = 58.0
SIGMA = 32.0   # corner smoothing in units
BOW = 0.015    # how far a straight stroke may bow, as a share of its length
ofont = ImageFont.truetype(ORIG, 1000); ASC, DESC = 1100, 320
def mask(ch):
    img = Image.new("L", (1100, ASC + DESC), 0)
    ImageDraw.Draw(img).text((50, ASC), ch, font=ofont, fill=255, anchor="ls")
    return np.array(img) > 127
def resample(pts, step=4.0):
    d = np.r_[0, np.cumsum(np.hypot(*np.diff(pts, axis=0).T))]
    if d[-1] < step: return pts
    t = np.r_[np.arange(0, d[-1], step), d[-1]]
    return np.stack([np.interp(t, d, pts[:, 0]), np.interp(t, d, pts[:, 1])], 1)
RINGS = []
def edges(ch):
    m = mask(ch); RINGS.clear()
    lab, n = ndimage.label(m)
    for c_ in range(1, n + 1):
        comp = lab == c_; ys_, xs_ = np.nonzero(comp)
        if np.ptp(xs_) > 220 or np.ptp(ys_) > 220: continue
        filled = ndimage.binary_fill_holes(comp)
        if filled.sum() - comp.sum() < 30: continue
        cx, cy = xs_.mean(), ys_.mean()
        hole_r = math.sqrt((filled.sum() - comp.sum()) / math.pi); out_r = math.sqrt(filled.sum() / math.pi)
        RINGS.append((np.array([cx - 50.0, ASC - cy]), (hole_r + out_r) / 2))
        m = m & ~comp
    dt = ndimage.distance_transform_edt(m); sk = skeletonize(m)
    if not sk.any(): return [], 0
    g = Skeleton(sk); paths = [g.path_coordinates(i) for i in range(g.n_paths)]
    r = float(np.median([dt[tuple(p)] for rc in paths for p in rc]))
    # prune spurs repeatedly
    while True:
        ends = {}
        for rc in paths:
            for e in (tuple(rc[0]), tuple(rc[-1])): ends[e] = ends.get(e, 0) + 1
        keep = []
        for rc in paths:
            f0, f1 = ends[tuple(rc[0])] == 1, ends[tuple(rc[-1])] == 1
            if (f0 != f1) and len(rc) < 1.6 * r: continue
            keep.append(rc)
        if len(keep) == len(paths): break
        paths = keep
    out = []
    for rc in paths:
        pts = np.array([[c - 50.0, ASC - rr] for rr, c in rc]); out.append(pts)
    out = drop_hook_branches(out)
    out = join_v_peaks(out)
    out = contract_nodes(out, 1.6 * r)
    out = drop_junction_spurs(out, 75.0)
    out = pair_merge(out)
    out = [despike(resample(p)) for p in out]
    res = []
    for p in out:
        for q in split_box_corners(resample(p)): res.append(trim_end_hooks(q))
    res = [p for p in res if len(p) > 1]
    return straighten_free_ends(res), r
def node_map(paths):
    ends = {}
    for i, p in enumerate(paths):
        for k, e in ((0, p[0]), (1, p[-1])): ends.setdefault((round(e[0]), round(e[1])), []).append((i, k))
    return ends
def contract_nodes(paths, lim):
    """Short pieces between two junctions are parts of one crossing: shrink each to its midpoint."""
    while True:
        ends = node_map(paths); hit = None
        for i, p in enumerate(paths):
            a, b = (round(p[0][0]), round(p[0][1])), (round(p[-1][0]), round(p[-1][1]))
            if a != b and len(ends[a]) > 1 and len(ends[b]) > 1 and arclen(p) < lim: hit = i; break
        if hit is None: return paths
        p = paths[hit]; mid = (p[0] + p[-1]) / 2
        a, b = (round(p[0][0]), round(p[0][1])), (round(p[-1][0]), round(p[-1][1]))
        new = []
        for j, q in enumerate(paths):
            if j == hit: continue
            q = q.copy()
            if (round(q[0][0]), round(q[0][1])) in (a, b): q = np.vstack([mid, q])
            if (round(q[-1][0]), round(q[-1][1])) in (a, b): q = np.vstack([q, mid])
            new.append(q)
        paths = new
def despike(p):
    """Cut a short out-and-back excursion (the skeleton running into a pointed corner and back)."""
    changed = True
    while changed and len(p) > 12:
        changed = False
        for w in (4, 8, 12, 16):
            for k in range(w, len(p) - w):
                if ang(p[k] - p[k - w], p[k + w] - p[k]) > 140:
                    p = np.vstack([p[: k - w + 1], p[k + w:]]); changed = True; break
            if changed: break
    return p
def drop_junction_spurs(paths, lim):
    """A short free branch at a junction is the square end or overshoot of a gothic stroke, not a stroke."""
    while True:
        ends = node_map(paths); hit = None
        for key, lst in ends.items():
            if len(lst) < 3: continue
            for i, k in lst:
                q = paths[i] if k == 0 else paths[i][::-1]
                far = ends[(round(q[-1][0]), round(q[-1][1]))]
                if len(far) == 1 and arclen(q) < lim: hit = i; break
            if hit is not None: break
        if hit is None: return paths
        del paths[hit]
def pair_merge(paths):
    """At every node, join the two branches that continue each other most directly (turn below 70 degrees)."""
    while True:
        ends = node_map(paths); best = None
        for key, lst in ends.items():
            if len(lst) < 2: continue
            br = []
            for i, k in lst:
                q = paths[i] if k == 0 else paths[i][::-1]          # starts at the node
                if len(q) < 2: continue
                d = np.r_[0, np.cumsum(np.hypot(*np.diff(q, axis=0).T))]
                j = int(np.searchsorted(d, min(120.0, d[-1])))
                br.append((i, k, unit(q[min(j, len(q) - 1)] - q[0])))
            for x in range(len(br)):
                for y in range(x + 1, len(br)):
                    if br[x][0] == br[y][0]: continue
                    a_ = ang(br[x][2], br[y][2])
                    ok = a_ >= 110 or len(br) == 2
                    if ok and (best is None or a_ > best[0]): best = (a_, br[x], br[y])
        if best is None: return paths
        _, (i, ki, _), (j, kj, _) = best
        a = paths[i] if ki == 1 else paths[i][::-1]     # ends at node
        b = paths[j] if kj == 0 else paths[j][::-1]     # starts at node
        # skip the bent skeleton around the node: cut both sides back and let the spline bridge the gap
        ca = int(np.searchsorted(np.r_[0, np.cumsum(np.hypot(*np.diff(a[::-1], axis=0).T))], min(40.0, 0.3 * arclen(a))))
        cb = int(np.searchsorted(np.r_[0, np.cumsum(np.hypot(*np.diff(b, axis=0).T))], min(40.0, 0.3 * arclen(b))))
        joined = np.vstack([a[:len(a) - ca] if ca else a, b[cb:] if cb else b[1:]])
        paths = [p for t, p in enumerate(paths) if t not in (i, j)] + [joined]
def endpoints_index(paths):
    ends = {}
    for i, p in enumerate(paths):
        for k, e in ((0, p[0]), (1, p[-1])): ends.setdefault((round(e[0] / 6), round(e[1] / 6)), []).append((i, k))
    return ends
def straighten_free_ends(paths, cut=40.0, look=100.0):
    """The last 40 units of a free end follow the direction of the 100 units before them."""
    ends = endpoints_index(paths); out = []
    for i, p in enumerate(paths):
        L = arclen(p)
        for k in (0, 1):
            e = p[0] if k == 0 else p[-1]
            if len(ends[(round(e[0] / 6), round(e[1] / 6))]) != 1 or L < 2 * (cut + look) or len(p) < 4: continue
            q = p if k == 1 else p[::-1]
            d = np.r_[0, np.cumsum(np.hypot(*np.diff(q, axis=0).T))]
            i1 = int(np.searchsorted(d, L - cut)); i0 = int(np.searchsorted(d, L - cut - look))
            t = unit(q[i1] - q[i0])
            tail = np.array([q[i1] + t * s_ for s_ in np.arange(4, cut + 4, 4)])
            q = np.vstack([q[:i1 + 1], tail])
            p = q if k == 1 else q[::-1]
        out.append(p)
    return out
def join_v_peaks(paths):
    """A short free spur between two branches that meet at an acute angle is the tip of a V: run the stroke through it."""
    changed = True
    while changed:
        changed = False
        ends = {}
        for i, p in enumerate(paths):
            for k, e in ((0, p[0]), (1, p[-1])): ends.setdefault((round(e[0]), round(e[1])), []).append((i, k))
        for key, lst in ends.items():
            if len(lst) != 3: continue
            outs = [(i, (paths[i] if k == 0 else paths[i][::-1])) for i, k in lst]   # each starts at the junction
            for si, sp in outs:
                far = ends[(round(sp[-1][0]), round(sp[-1][1]))]
                if len(far) != 1 or arclen(sp) > 160: continue
                others = [(i, q) for i, q in outs if i != si]
                if any(arclen(q) < 1.5 * arclen(sp) for _, q in others): continue
                u1 = unit(others[0][1][min(40, len(others[0][1]) - 1)] - others[0][1][0])
                u2 = unit(others[1][1][min(40, len(others[1][1]) - 1)] - others[1][1][0])
                if ang(u1, u2) > 100: continue
                if ang(sp[-1] - sp[0], -(u1 + u2)) > 35: continue
                a = others[0][1][::-1]; b = others[1][1]
                k_ = min(10, len(a) // 4, len(b) // 4)
                joined = np.vstack([a[:len(a) - k_], [sp[-1]], b[k_:]])
                keep = [p for j, p in enumerate(paths) if j not in (si, others[0][0], others[1][0])]
                paths = keep + [joined]; changed = True; break
            if changed: break
    return paths
def unit(v):
    n = np.hypot(*v); return v / n if n > 1e-9 else v
def ang(u, v): return math.degrees(math.acos(np.clip(unit(u) @ unit(v), -1, 1)))
def arclen(p): return float(np.hypot(*np.diff(p, axis=0).T).sum())
def drop_hook_branches(paths):
    """A short free branch that doubles back at a junction is a hook flick: drop it."""
    while True:
        ends = {}
        for i, p in enumerate(paths):
            for k, e in ((0, p[0]), (1, p[-1])): ends.setdefault((round(e[0]), round(e[1])), []).append((i, k))
        drop = None
        for key, lst in ends.items():
            if len(lst) != 3: continue
            for (i, k) in lst:
                p = paths[i] if k == 0 else paths[i][::-1]        # p starts at the junction
                other_free = ends[(round(p[-1][0]), round(p[-1][1]))]
                if len(other_free) != 1 or arclen(p) > 200: continue
                out_dir = p[-1] - p[0]
                for (j, kj) in lst:
                    if j == i: continue
                    q = paths[j] if kj == 1 else paths[j][::-1]   # q ends at the junction
                    if arclen(q) < 2 * arclen(p): continue
                    in_dir = q[-1] - q[max(0, len(q) - 80)]
                    # a hook flick has a short free heel beside it (the V of the gothic hook). A loop tail does not.
                    heels = [g for (g, kg) in lst if g not in (i, j)
                             and len(ends[(round((paths[g] if kg == 0 else paths[g][::-1])[-1][0]), round((paths[g] if kg == 0 else paths[g][::-1])[-1][1]))]) <= 2
                             and arclen(paths[g]) < 260
                             and ang(in_dir, (paths[g] if kg == 0 else paths[g][::-1])[-1] - (paths[g] if kg == 0 else paths[g][::-1])[0]) < 45]
                    if heels and ang(in_dir, out_dir) > 100:
                        far_in = q[-1] - q[0]
                        drop = (i, j, unit(far_in), key)
            if drop is not None: break
        if drop is None: return paths
        i, j, dirn, key = drop
        for (h, kh) in ends[key]:
            if h in (i, j): continue
            heel = paths[h] if kh == 0 else paths[h][::-1]
            far = ends.get((round(heel[-1][0]), round(heel[-1][1])), [])
            if arclen(heel) > 260: continue
            # the heel may continue through a small node: follow it to the free end
            tip = heel[-1]
            for (g, kg) in far:
                if g != h:
                    nxt = paths[g] if kg == 0 else paths[g][::-1]
                    if arclen(nxt) < 200: tip = nxt[-1]; paths[g] = nxt[:1]
            reach = max(0.0, float((tip - heel[0]) @ dirn))
            # cut the main stroke back 40 units, then run straight to the old tip
            for (m_, km) in ends[key]:
                if m_ in (i, h): continue
                mp = paths[m_] if km == 1 else paths[m_][::-1]
                if len(mp) > 80:
                    base = mp[-40]; paths[m_] = mp[:-39] if km == 1 else mp[:-39][::-1]
                    reach += float((heel[0] - base) @ dirn)
                    paths[h] = np.array([base + dirn * t for t in np.linspace(0, reach, max(2, int(reach / 4)))])
                    # keep the joint for merge: the main now ends at base
                    break
            else:
                paths[h] = np.array([heel[0] + dirn * t for t in np.linspace(0, reach, max(2, int(reach / 4)))])
        del paths[i]
        paths = [p for p in paths if len(p) > 1]
def split_box_corners(p):
    """Down-then-left (or right-then-up) corners are where a hand lifts the pen: split there."""
    if len(p) < 30: return [p]
    W = 10; cuts = []
    for k in range(W, len(p) - W):
        a, b = p[k] - p[k - W], p[k + W] - p[k]
        if ang(a, b) < 60: continue
        da, db = math.degrees(math.atan2(a[1], a[0])), math.degrees(math.atan2(b[1], b[0]))
        down_left = abs(da + 90) < 30 and (abs(db) > 150)
        right_up = abs(da) < 30 and abs(db - 90) < 30
        if down_left or right_up:
            if not cuts or k - cuts[-1] > 2 * W: cuts.append(k)
            elif ang(p[k] - p[k - W], p[k + W] - p[k]) > ang(p[cuts[-1]] - p[cuts[-1] - W], p[cuts[-1] + W] - p[cuts[-1]]): cuts[-1] = k
    if not cuts: return [p]
    parts, s = [], 0
    for c in cuts: parts.append(p[s:c + 1]); s = c
    parts.append(p[s:])
    LEAN = math.tan(math.radians(5))
    for i, c in enumerate(cuts):
        a = p[c] - p[c - W]
        if abs(math.degrees(math.atan2(a[1], a[0])) + 90) < 30:
            q = parts[i].copy(); k = len(q) - 1
            while k > W and abs(math.degrees(math.atan2(*(q[k] - q[k - W])[::-1])) + 90) < 25: k -= 1
            if len(q) - k > 15:
                y0 = q[k][1]; q[k:, 0] -= (y0 - q[k:, 1]) * LEAN; parts[i] = q
    # the horizontal stroke runs a little past the vertical, so the joint reads as two strokes
    OVER = 22
    for i, c in enumerate(cuts):
        a = p[c] - p[c - W]; down_left = abs(math.degrees(math.atan2(a[1], a[0])) + 90) < 30
        if down_left:
            q = parts[i + 1]; d = unit(q[min(8, len(q) - 1)] - q[0]); parts[i + 1] = np.vstack([q[0] - d * OVER, q])
        else:
            q = parts[i]; d = unit(q[-1] - q[max(0, len(q) - 9)]); parts[i] = np.vstack([q, q[-1] + d * OVER])
    return parts
def trim_end_hooks(p):
    """Cut a flick at either end: a sharp local turn within 150 units, or a bent stub within 60 units."""
    for _ in range(2):
        if len(p) > 50:
            cut = None; best = 0
            for k in range(4, min(38, len(p) - 40)):
                t = ang(p[k] - p[k - 4], p[k + 6] - p[k])
                if t > 50 and t > best: best, cut = t, k
            if cut is None:
                for k in range(3, min(16, len(p) - 40)):
                    t = ang(p[k] - p[0], p[k + 40] - p[k])
                    if t > 28 and t > best: best, cut = t, k
            if cut is not None and arclen(p[cut:]) > 2.5 * arclen(p[:cut + 1]): p = p[cut:]
        p = p[::-1]
    return p
def merge(paths):
    """Join edges that meet at a degree-2 node (left after pruning) into one stroke."""
    paths = [p for p in paths if len(p) > 1]
    changed = True
    while changed:
        changed = False
        ends = {}
        for i, p in enumerate(paths):
            for k, e in ((0, p[0]), (1, p[-1])): ends.setdefault((round(e[0]), round(e[1])), []).append((i, k))
        for key, lst in ends.items():
            if len(lst) == 2 and lst[0][0] != lst[1][0]:
                (i, ki), (j, kj) = lst
                a = paths[i] if ki == 1 else paths[i][::-1]
                b = paths[j] if kj == 0 else paths[j][::-1]
                paths[i] = np.vstack([a, b[1:]]); del paths[j]; changed = True; break
    return paths
from scipy.interpolate import make_lsq_spline
R_CORNER = 40
def bow(p, seed):
    c = p[-1] - p[0]; L = np.hypot(*c)
    if L < 120: return p
    n = np.array([-c[1], c[0]]) / L
    if np.abs((p - p[0]) @ n).max() > 0.04 * L: return p
    rnd = (zlib.crc32(seed.encode()) % 1000) / 1000 - 0.5
    an = abs(math.degrees(math.atan2(c[1], c[0]))) % 180
    base = 0.01 if an < 30 or an > 150 else -0.01 if 60 < an < 120 else 0
    if an > 90: n = -n
    t = np.linspace(0, 1, len(p))[:, None]
    return p + n * (base + rnd * 2 * BOW) * L * 4 * t * (1 - t)
def corners(p, W=6, th=55):
    out = []
    for k in range(W, len(p) - W):
        t = ang(p[k] - p[k - W], p[k + W] - p[k])
        if t > th:
            if out and k - out[-1][0] <= 2 * W:
                if t > out[-1][1]: out[-1] = (k, t)
            else: out.append((k, t))
    return [k for k, _ in out]
class Seg:
    """A smooth centerline piece: a least-squares cubic spline x(u), y(u) over arclength u."""
    def __init__(self, p):
        d = np.r_[0, np.cumsum(np.hypot(*np.diff(p, axis=0).T))]; self.L = d[-1]
        if self.L < 50 or len(p) < 6 or (self.L < 160 and np.abs((p - p[0]) @ np.array([-(p[-1]-p[0])[1], (p[-1]-p[0])[0]]) / max(self.L, 1)).max() < 12):
            self.line = (p[0], p[-1]); return
        self.line = None
        for m in range(0, max(1, int(self.L / 90))):
            t = np.r_[[0] * 4, np.linspace(0, self.L, m + 2)[1:-1], [self.L] * 4]
            try:
                sx = make_lsq_spline(d, p[:, 0], t, 3); sy = make_lsq_spline(d, p[:, 1], t, 3)
            except (ValueError, np.linalg.LinAlgError): continue   # too many knots for the points
            dev = np.hypot(sx(d) - p[:, 0], sy(d) - p[:, 1]).max()
            self.sx, self.sy, self.t = sx, sy, t
            if dev < 8: break
    def pt(self, u):
        if self.line: a, b = self.line; return a + (b - a) * (u / max(self.L, 1e-9))
        return np.array([float(self.sx(u)), float(self.sy(u))])
    def tan(self, u):
        if self.line: a, b = self.line; return unit(b - a)
        return unit(np.array([float(self.sx(u, 1)), float(self.sy(u, 1))]))
    def beziers(self, u0, u1):
        if self.line or u1 - u0 < 1e-6:
            a, b = self.pt(u0), self.pt(u1); return [(a, a + (b - a) / 3, b - (b - a) / 3, b)]
        ks = [u0] + [k for k in np.unique(self.t) if u0 < k < u1] + [u1]; out = []
        for a, b in zip(ks, ks[1:]):
            h = (b - a) / 3
            P0 = self.pt(a); P3 = self.pt(b)
            D0 = np.array([float(self.sx(a, 1)), float(self.sy(a, 1))]); D1 = np.array([float(self.sx(b, 1)), float(self.sy(b, 1))])
            out.append((P0, P0 + D0 * h, P3 - D1 * h, P3))
        return out
def stroke_beziers(p, seed):
    p = bow(resample(p), seed)
    ks = corners(p); cuts = [0] + ks + [len(p) - 1]
    segs = [Seg(p[a:b + 1]) for a, b in zip(cuts, cuts[1:])]
    lim = [[0.0, s.L] for s in segs]
    fil = []
    for i in range(len(segs) - 1):
        A, B = segs[i], segs[i + 1]
        T1, T2 = A.tan(A.L), B.tan(0.0); th = math.radians(ang(T1, T2))
        t = R_CORNER * math.tan(th / 2)
        t = min(t, 45.0, 0.45 * A.L, 0.45 * B.L)
        lim[i][1] = A.L - t; lim[i + 1][0] = t
        fil.append(th)
    out = []
    for i, s in enumerate(segs):
        out += s.beziers(*lim[i])
        if i < len(segs) - 1:
            A, B = segs[i], segs[i + 1]
            E, S = A.pt(lim[i][1]), B.pt(lim[i + 1][0]); T1, T2 = A.tan(lim[i][1]), B.tan(lim[i + 1][0])
            ch = np.hypot(*(S - E)); h = ch / (2 * math.cos(fil[i] / 2)) * 4 / 3 * math.tan(fil[i] / 4) / max(math.tan(fil[i] / 2), 1e-6)
            h = min(h, ch * 0.6)
            out.append((E, E + T1 * h, S - T2 * h, S))
    return out
mono = TTFont(MONO); cm = mono.getBestCmap(); glyf = mono["glyf"]; gs = mono.getGlyphSet()
for cp_, nm in ((0x3095, "uni3095"), (0x3096, "uni3096")):      # ゕ ゖ: not in the original, added here
    if cp_ in cm: continue
    order = mono.getGlyphOrder(); order.append(nm); mono.setGlyphOrder(order)
    glyf[nm] = TTGlyphPen(None).glyph(); mono["hmtx"][nm] = (1000, 0)
    for t_ in mono["cmap"].tables:
        if t_.isUnicode(): t_.cmap[cp_] = nm
cm = mono.getBestCmap(); gs = mono.getGlyphSet()
ORIG_CMAP = TTFont(ORIG).getBestCmap()
KANA = [cp for cp in list(range(0x3041, 0x3097)) + list(range(0x30A1, 0x30FB)) + [0x30FC] if cp in cm]
skels = {}; RING_OF = {}
for cp in KANA:
    if cp not in ORIG_CMAP: continue                 # nothing to trace (ゕ ゖ are built from か け)
    e, r = edges(chr(cp))
    if e: skels[cp] = e
    if RINGS: RING_OF[cp] = list(RINGS)
def eta_ri(e):
    """り drawn like η: an arch springs from the middle of the left stroke and runs into the right stroke."""
    L, R = sorted(e, key=lambda p: min(p[:, 0]))
    if L[0][1] < L[-1][1]: L = L[::-1]
    if R[0][1] < R[-1][1]: R = R[::-1]                      # both run top to bottom
    dL = np.r_[0, np.cumsum(np.hypot(*np.diff(L, axis=0).T))]; dR = np.r_[0, np.cumsum(np.hypot(*np.diff(R, axis=0).T))]
    S = L[int(np.searchsorted(dL, 0.55 * dL[-1]))]
    j = int(np.searchsorted(dR, 90)); Rj = R[j]; tR = unit(R[min(j + 10, len(R) - 1)] - Rj)
    P0, P1, P2, P3 = S, S + np.array([30.0, 190.0]), Rj - tR * 150, Rj
    t = np.linspace(0, 1, 60)[:, None]
    arch = (1 - t) ** 3 * P0 + 3 * (1 - t) ** 2 * t * P1 + 3 * (1 - t) * t * t * P2 + t ** 3 * P3
    return [L, np.vstack([arch, R[j + 1:]])]
ORIG_SK = {k: list(v) for k, v in skels.items()}
if 0x308A in skels and len(skels[0x308A]) == 2: skels[0x308A] = eta_ri(skels[0x308A])
def wa_family(e):
    """わ ね れ in stroke order: the vertical, then the bar turning like ㄱ into the down-left diagonal,
    and the right part leaving that diagonal where it crosses the vertical."""
    allp = np.vstack(e)
    xs_ = np.round(allp[:, 0]).astype(int); vals, counts = np.unique(xs_, return_counts=True)
    vx = float(vals[np.argmax(np.convolve(counts, np.ones(9), "same"))])
    near = allp[np.abs(allp[:, 0] - vx) < 15]
    vtop, vbot = near[:, 1].max(), near[:, 1].min()
    vertical = np.array([[vx, y] for y in np.linspace(vtop, vbot, 60)])
    bars = [p for p in e if np.ptp(p[:, 0]) > 2.5 * np.ptp(p[:, 1]) and arclen(p) < 350 and p[:, 1].mean() > 0.6 * vtop]
    bar = max(bars, key=lambda p: p[:, 1].mean())
    if bar[0][0] > bar[-1][0]: bar = bar[::-1]
    left_pts = allp[(allp[:, 0] < vx - 20) & (allp[:, 1] < bar[:, 1].min() - 40)]
    D = left_pts[np.argmin(left_pts[:, 1] + 0.3 * left_pts[:, 0])]
    T = np.array([max(bar[-1][0], vx + 60), bar[-1][1]])
    keep_bar = bar[bar[:, 0] < T[0] - 4]
    diag = np.array([T + (D - T) * t for t in np.linspace(0, 1, 60)])
    stroke2 = np.vstack([keep_bar, diag])
    runs = []
    for p in e:
        if p is bar: continue
        mask_ = p[:, 0] > vx + 30
        i = 0
        while i < len(p):
            if mask_[i]:
                j = i
                while j < len(p) and mask_[j]: j += 1
                runs.append(p[i:j]); i = j
            else: i += 1
    run = max(runs, key=arclen)
    if abs(run[-1][0] - vx) < abs(run[0][0] - vx): run = run[::-1]
    tj = (vx + 12 - T[0]) / (D[0] - T[0]); J = T + (D - T) * tj
    back = np.array([D + (J - D) * t for t in np.linspace(0, 1, 40)])
    right = bridge(back, run)
    return [vertical, stroke2, right]
def retrace_into(main, branch):
    """main runs to its lowest end; the branch then starts there, goes back along main to where it used to leave it, and on."""
    if main[0][1] < main[-1][1]: main = main[::-1]                      # ends at the lowest point
    d0 = np.hypot(*(main - branch[0]).T).min(); d1 = np.hypot(*(main - branch[-1]).T).min()
    if d1 < d0: branch = branch[::-1]
    idx = int(np.argmin(np.hypot(*(main - branch[0]).T)))
    back = main[idx:][::-1]
    return main, bridge(back, branch)
def bridge(a, b, gap=50.0):
    """Join a to b leaving out the bent stretch around the joint, so the spline passes smoothly."""
    da = np.r_[0, np.cumsum(np.hypot(*np.diff(a[::-1], axis=0).T))]; db = np.r_[0, np.cumsum(np.hypot(*np.diff(b, axis=0).T))]
    ka = int(np.searchsorted(da, min(gap, 0.4 * da[-1]))); kb = int(np.searchsorted(db, min(gap, 0.4 * db[-1])))
    return np.vstack([a[: len(a) - ka] if ka else a, b[kb:] if kb else b[1:]])
def loop_from_bottom(e):
    bowl = max(e, key=arclen)
    others = [p for p in e if p is not bowl]
    dist = lambda p: min(np.hypot(*(p - bowl[0]).T).min(), np.hypot(*(p - bowl[-1]).T).min())
    main = min(others, key=dist)
    if dist(main) > 60: return e                 # the bowl already carries on from its stroke, the rest stays apart
    m2, b2 = retrace_into(main, bowl)
    return [p for p in others if p is not main] + [m2, b2]
for cp_ in (0x308B, 0x308D, 0x3089):
    if cp_ in skels:
        skels[cp_] = loop_from_bottom(skels[cp_])
for cp_ in (0x308F, 0x306D, 0x308C, 0x308E):
    if cp_ in skels:
        skels[cp_] = wa_family(skels[cp_])
def we_build(cp_):
    """ゑ: the Z, then one stroke round the bowl, down to the bottom left and along the wave; the small loop is a circle."""
    e = ORIG_SK[cp_]
    z = max(e, key=lambda p: p[:, 1].max())
    wave = min(e, key=lambda p: p[:, 1].mean())
    rest = [p for p in e if p is not z and p is not wave]
    bowl = max(rest, key=arclen)
    lo_end = min(bowl[0][1], bowl[-1][1])
    if lo_end < wave[:, 1].min() + 40:
        # the bowl came out joined to the first hill's left leg: split it there and give the leg back to the wave
        b = bowl if bowl[0][1] < bowl[-1][1] else bowl[::-1]
        w = wave if np.hypot(*(wave[0] - b[0])) < np.hypot(*(wave[-1] - b[0])) else wave
        ends_w = [w[0], w[-1]]
        j = min(range(len(b)), key=lambda i: min(np.hypot(*(b[i] - q)) for q in ends_w))
        leg, bowl = b[: j + 1], b[j:]
        w = w if np.hypot(*(w[0] - leg[-1])) < np.hypot(*(w[-1] - leg[-1])) else w[::-1]
        wave = np.vstack([leg, w[1:]])
    if z[0][1] < z[-1][1]: z = z[::-1]
    if wave[0][0] > wave[-1][0]: wave = wave[::-1]
    if bowl[0][1] < bowl[-1][1]: bowl = bowl[::-1]
    j = int(np.argmin(np.hypot(*(wave - bowl[-1]).T)))               # where the bowl lands on the first hump
    leg = wave[: j + 1]
    m = mask(chr(cp_)); holes = ndimage.binary_fill_holes(m) & ~m
    lab, n = ndimage.label(holes)
    sizes = ndimage.sum(holes, lab, range(1, n + 1)); k = int(np.argmin(sizes)) + 1
    ys_, xs_ = np.nonzero(lab == k); hr = math.sqrt(len(xs_) / math.pi)
    rr = float(np.median(ndimage.distance_transform_edt(m)[skeletonize(m)]))
    C = np.array([xs_.mean() - 50.0, ASC - ys_.mean()]); rc = hr + rr
    # the bowl passes under the loop heading left. There it curls once round the loop, clockwise.
    bottom = C - np.array([0.0, rc])
    kb = int(np.argmin(np.hypot(*(bowl - bottom).T)))
    angs = np.linspace(-math.pi / 2, -math.pi / 2 - 2 * math.pi, 90)
    curl = np.c_[C[0] + rc * np.cos(angs), C[1] + rc * np.sin(angs)]
    D = wave[0]; E = curl[-1]
    pk = int(np.argmax(wave[: len(wave) // 2, 1])); P = wave[pk]
    to_p = np.array([E + (P - E) * t for t in np.linspace(0, 1, 40)])
    leg = np.array([P + (D - P) * t for t in np.linspace(0, 1, 40)])
    z, zb = retrace_into(z if z[0][1] > z[-1][1] else z[::-1], bowl[: kb + 1])
    s2 = np.vstack([zb, curl, bridge(curl[-12:], to_p)[12:], leg[1:]])   # round the loop, over the hump top, down to the bottom left
    s3 = bridge(leg[::-1], wave[pk:], 30.0)                             # back up the same line and over both hills
    return [z, s2, s3]
if 0x3091 in skels:
    skels[0x3091] = we_build(0x3091)
def straight_vertical(e):
    v = max(e, key=lambda p: np.ptp(p[:, 1]))
    top = v[np.argmax(v[:, 1])]; bot_y = v[:, 1].min()
    near = [p for p in e if p is not v and arclen(p) < 220 and np.hypot(*(p - np.array([top[0], bot_y])).T).min() < 120]
    for p in near: bot_y = min(bot_y, p[:, 1].min())
    line = np.array([[top[0], y] for y in np.linspace(top[1], bot_y, 60)])
    return [p for p in e if p is not v and not any(p is q for q in near)] + [line]
# the left vertical of け に は ほ (and their voiced forms) is the Kkomi ㅣ
def kkomi_i_profile():
    f_ = ImageFont.truetype(MONO, 1000); img = Image.new("L", (1100, ASC + DESC), 0)
    ImageDraw.Draw(img).text((50, ASC), "ㅣ", font=f_, fill=255, anchor="ls")
    sk = skeletonize(np.array(img) > 127); g_ = Skeleton(sk)
    p = max((g_.path_coordinates(i) for i in range(g_.n_paths)), key=len)
    p = np.array([[c - 50.0, ASC - r_] for r_, c in p])
    if p[0][1] < p[-1][1]: p = p[::-1]
    p = p[len(p) // 12: len(p) - len(p) // 12]            # drop the end forks
    L = p[0][1] - p[-1][1]; return (p - p[0]) / L          # top at 0, falls by 1
I_PROFILE = kkomi_i_profile()
ax_guess, ay_guess = 0.926, 1.049   # the skeleton-to-Mono scale (fitted below), for the ㅣ aspect
LEFT_I = [0x3051, 0x3052, 0x306B, 0x306F, 0x3070, 0x3071, 0x307B, 0x307C, 0x307D]
# dakuten: two short marks at the top right, with a thinner pen and a clear gap
import unicodedata
MARKS = {}
for cp_, e in list(skels.items()):
    if "3099" not in unicodedata.decomposition(chr(cp_)): continue
    allp = np.vstack(e); x0, x1 = allp[:, 0].min(), allp[:, 0].max(); y0, y1 = allp[:, 1].min(), allp[:, 1].max()
    marks = [p for p in e if arclen(p) < 170 and p[:, 0].mean() > x0 + 0.45 * (x1 - x0) and p[:, 1].mean() > y0 + 0.55 * (y1 - y0)]
    if len(marks) != 2: raise SystemExit(f"{chr(cp_)}: found {len(marks)} dakuten strokes, not 2")
    marks.sort(key=lambda p: p[:, 0].mean())
    c1, c2 = marks[0].mean(0), marks[1].mean(0); M = (c1 + c2) / 2; v = unit(c2 - c1)
    new = []
    for c_, p, sgn in ((c1, marks[0], -1), (c2, marks[1], 1)):
        d = unit(p[-1] - p[0]); d = d if d[1] < 0 else -d
        cc = M + v * sgn * 48
        new.append(np.array([cc - d * 44, cc + d * 44]))
    MARKS[cp_] = new
    skels[cp_] = [p for p in e if not any(p is m for m in marks)]
for cp_ in (0x30DB, 0x30DC, 0x30DD):
    if cp_ in skels: skels[cp_] = straight_vertical(skels[cp_])
if 0x30C8 in skels and 0x30C9 in skels: skels[0x30C8] = [p.copy() for p in skels[0x30C9]]
if 0x30DB in skels and 0x30DC in skels: skels[0x30DB] = [p.copy() for p in skels[0x30DC]]
if 0x30F4 in skels and 0x30A6 in skels: skels[0x30F4] = [p.copy() for p in skels[0x30A6]]
def seg_line(a, b, n=40): return np.array([a + (b - a) * t for t in np.linspace(0, 1, n)])
def build_mu(e):
    """ム: the short right stroke runs on past the end of the bottom bar."""
    t0 = min(e, key=arclen); t = t0 if t0[0][1] > t0[-1][1] else t0[::-1]   # top to bottom
    d = unit(t[-1] - t[max(0, len(t) - 15)])
    return [p for p in e if p is not t0] + [np.vstack([t, [t[-1] + d * 80]])]
def build_ya(e):
    """ヤ: the bar turns straight into the short down-left stroke, with no corner sticking out."""
    bar0 = max(e, key=lambda p: np.ptp(p[:, 0])); bar = bar0[::-1] if bar0[0][0] > bar0[-1][0] else bar0
    c = int(np.argmax(bar[:, 1])); end = bar[-1]
    return [p for p in e if p is not bar0] + [np.vstack([bar[: c + 1], seg_line(bar[c], end)[1:]])]
def build_i(e):
    """イ: one diagonal from the top right to the bottom left; the vertical starts from its middle."""
    P1 = max(e, key=arclen); P2 = [p for p in e if p is not P1][0]
    if P1[0][1] < P1[-1][1]: P1 = P1[::-1]
    if P2[0][0] < P2[-1][0]: P2 = P2[::-1]                      # runs to the bottom left
    j = int(np.argmin(np.hypot(*(P1 - P2[0]).T)))
    return [bridge(P1[: j + 1], P2, 30.0), P1[j:]]
def build_ra(e):
    """ら: the vertical runs straight to its lowest point and turns there into the bowl."""
    P0 = max(e, key=arclen); P = P0[::-1] if P0[0][1] < P0[-1][1] else P0
    i = int(np.argmin(P[: len(P) // 2, 1]))
    return [p for p in e if p is not P0] + [np.vstack([seg_line(P[0], P[i]), P[i + 1:]])]
def build_hmu(e):
    """む: the second stroke comes down, loops round on the left, comes back to the vertical and runs on."""
    V0 = max(e, key=arclen)
    L0 = max([p for p in e if p is not V0 and np.ptp(p[:, 1]) > 150], key=arclen)
    V = V0[::-1] if V0[0][1] < V0[-1][1] else V0               # from the top down
    loop = L0[::-1] if L0[0][1] < L0[-1][1] else L0            # leaves the vertical at its upper end
    i1 = int(np.argmin(np.hypot(*(V - loop[0]).T))); i2 = int(np.argmin(np.hypot(*(V - loop[-1]).T)))
    arc = np.vstack([V[i1], loop[3:-3], V[i2]])               # the loop closes on the vertical at both ends
    return [p for p in e if p is not V0 and p is not L0] + [V, arc]
def build_re(e):
    """れ: the tail turns up once; the last flick is cut."""
    R0 = max(e, key=lambda p: p[:, 0].max()); R = R0[::-1] if R0[0][0] > R0[-1][0] else R0
    d = np.r_[0, np.cumsum(np.hypot(*np.diff(R, axis=0).T))]
    return [p for p in e if p is not R0] + [R[: int(np.searchsorted(d, d[-1] - 90))]]
for cp_, fn in ((0x3089, build_ra), (0x3080, build_hmu), (0x308C, build_re)):
    if cp_ in skels:
        skels[cp_] = fn(skels[cp_])
for cp_, fn in ((0x30E0, build_mu), (0x30E4, build_ya), (0x30A4, build_i)):
    if cp_ in skels:
        skels[cp_] = fn(skels[cp_])
for cp_ in LEFT_I:
    if cp_ not in skels: continue
    e = list(skels[cp_])
    cand = [i for i, q in enumerate(e) if np.ptp(q[:, 0]) < 0.35 * np.ptp(q[:, 1]) and np.ptp(q[:, 1]) > 280]
    if not cand: continue
    li = min(cand, key=lambda i: e[i][:, 0].mean()); q = e[li]
    top = q[np.argmax(q[:, 1])]; L = np.ptp(q[:, 1])
    e[li] = top + np.c_[I_PROFILE[:, 0] * L * ay_guess / ax_guess, I_PROFILE[:, 1] * L]
    skels[cp_] = e
# small kana are the large ones, scaled into the small glyph's box
SMALL = {0x3041: 0x3042, 0x3043: 0x3044, 0x3045: 0x3046, 0x3047: 0x3048, 0x3049: 0x304A, 0x3063: 0x3064,
         0x3083: 0x3084, 0x3085: 0x3086, 0x3087: 0x3088, 0x308E: 0x308F, 0x3095: 0x304B, 0x3096: 0x3051,
         0x30A1: 0x30A2, 0x30A3: 0x30A4, 0x30A5: 0x30A6, 0x30A7: 0x30A8, 0x30A9: 0x30AA, 0x30C3: 0x30C4,
         0x30E3: 0x30E4, 0x30E5: 0x30E6, 0x30E7: 0x30E8, 0x30EE: 0x30EF, 0x30F5: 0x30AB, 0x30F6: 0x30B1}
BORROW = {0x3095: (0x30F5, 0x30AB), 0x3096: (0x30F6, 0x30B1)}   # size and place from ヵ/カ and ヶ/ケ
for sm, lg in SMALL.items():
    if lg not in skels: continue
    if sm not in ORIG_SK:
        if sm not in BORROW or not all(c_ in ORIG_SK for c_ in BORROW[sm]): continue
        ks, kl = (np.vstack(ORIG_SK[c_]) for c_ in BORROW[sm]); lo_ = np.vstack(ORIG_SK[lg])
        k = min(np.ptp(ks[:, 0]) / np.ptp(kl[:, 0]), np.ptp(ks[:, 1]) / np.ptp(kl[:, 1]))
        bc = lambda a: np.array([(a[:, 0].min() + a[:, 0].max()) / 2, a[:, 1].min()])
        c_l = bc(lo_); c_s = c_l + (bc(ks) - bc(kl))
        skels[sm] = [c_s + (p - c_l) * k for p in skels[lg]]
        continue
    so = np.vstack(ORIG_SK[sm]); lo_ = np.vstack(ORIG_SK[lg])
    k = min(np.ptp(so[:, 0]) / np.ptp(lo_[:, 0]), np.ptp(so[:, 1]) / np.ptp(lo_[:, 1]))
    c_s = np.array([(so[:, 0].min() + so[:, 0].max()) / 2, so[:, 1].min()]); c_l = np.array([(lo_[:, 0].min() + lo_[:, 0].max()) / 2, lo_[:, 1].min()])
    skels[sm] = [c_s + (p - c_l) * k for p in skels[lg]]
    if lg in RING_OF: RING_OF[sm] = [(c_s + (c0 - c_l) * k, rr * k) for c0, rr in RING_OF[lg]]
NATIVE = {}
if 0x30FC in cm and 0x30FC not in skels:   # the original has no long vowel mark: a flat bar in the Mono box
    g = glyf[cm[0x30FC]]; y = (g.yMin + g.yMax) / 2
    NATIVE[0x30FC] = [np.array([[g.xMin + PEN / 2, y], [g.xMax - PEN / 2, y]])]
# affine fit original skeleton box -> mono ink box (pen-padded)
xs, ys = [], []
for cp, e in ORIG_SK.items():
    allp = np.vstack(e); g = glyf[cm[cp]]
    if g.numberOfContours <= 0: continue
    xs += [(allp[:, 0].min(), g.xMin + PEN / 2), (allp[:, 0].max(), g.xMax - PEN / 2)]
    ys += [(allp[:, 1].min(), g.yMin + PEN / 2), (allp[:, 1].max(), g.yMax - PEN / 2)]
def fit(pairs):
    a = np.array(pairs); A = np.c_[a[:, 0], np.ones(len(a))]; return np.linalg.lstsq(A, a[:, 1], rcond=None)[0]
(ax, bx), (ay, by) = fit(xs), fit(ys)
for cp, e in list(skels.items()) + list(NATIVE.items()):
    p = pathops.Path(); pen = p.getPen()
    for i, s in enumerate(e):
        if cp not in NATIVE: s = np.c_[s[:, 0] * ax + bx, s[:, 1] * ay + by]
        bz = stroke_beziers(s, f"{cp}-{i}")
        pen.moveTo(tuple(bz[0][0]))
        for b in bz:
            pen.curveTo(tuple(b[1]), tuple(b[2]), tuple(b[3]))
        pen.endPath()
    if cp in MARKS:
        mp_ = pathops.Path(); mpen = mp_.getPen()
        for m in MARKS[cp]:
            m = np.c_[m[:, 0] * ax + bx, m[:, 1] * ay + by]
            mpen.moveTo(tuple(m[0])); mpen.lineTo(tuple(m[1])); mpen.endPath()
        mp_.stroke(PEN * 0.8, pathops.LineCap.ROUND_CAP, pathops.LineJoin.ROUND_JOIN, 4); mp_.convertConicsToQuads()
    for (c0, rr) in RING_OF.get(cp, []):
        c0 = np.array([c0[0] * ax + bx, c0[1] * ay + by]); rr = rr * (ax + ay) / 2; h = 0.5523 * rr
        P = [c0 + rr * np.array(v) for v in ((1, 0), (0, 1), (-1, 0), (0, -1))]
        T = [np.array(v) for v in ((0, 1), (-1, 0), (0, -1), (1, 0))]
        pen.moveTo(tuple(P[0]))
        for q in range(4):
            a_, b_ = P[q], P[(q + 1) % 4]; pen.curveTo(tuple(a_ + T[q] * h), tuple(b_ - T[(q + 1) % 4] * h), tuple(b_))
        pen.closePath()
    p.stroke(PEN, pathops.LineCap.ROUND_CAP, pathops.LineJoin.ROUND_JOIN, 4)
    p.convertConicsToQuads()
    if cp in MARKS: p = pathops.op(p, mp_, pathops.PathOp.UNION)
    p.simplify()
    tt = TTGlyphPen(gs); p.draw(Cu2QuPen(tt, 1.0, reverse_direction=True))
    g = tt.glyph(); g.recalcBounds(glyf); glyf[cm[cp]] = g
    mono["hmtx"][cm[cp]] = (mono["hmtx"][cm[cp]][0], g.xMin)
# stars: the same round pen along the star outline. The filled star also fills the inside.
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.basePen import BasePen
class Flat(BasePen):
    def __init__(s_): super().__init__(None); s_.pts = []; s_.cur = []
    def _moveTo(s_, p): s_.cur = [p]
    def _lineTo(s_, p): s_.cur.append(p)
    def _qCurveToOne(s_, a, b):
        p0 = s_.cur[-1]
        for t in np.linspace(0, 1, 8)[1:]: s_.cur.append(tuple((1 - t) ** 2 * np.array(p0) + 2 * (1 - t) * t * np.array(a) + t * t * np.array(b)))
    def _curveToOne(s_, a, b, c): s_.cur.append(c)
    def _closePath(s_): s_.pts.append(s_.cur); s_.cur = []
def star_centerline(name):
    # a regular star that fits the half-width cell with the pen around it
    adv = mono["hmtx"][name][0]; c = np.array([adv / 2, 380.0])
    R = (adv - 50 - PEN) / (2 * math.sin(math.radians(72))); ri = 0.47 * R
    return np.array([c + (R if k % 2 == 0 else ri) * np.array([math.cos(math.pi / 2 + k * math.pi / 5), math.sin(math.pi / 2 + k * math.pi / 5)]) for k in range(10)]), (c, R, ri)
def filleted(C, r_tip, r_in):
    p = pathops.Path(); pen = p.getPen(); n = len(C); pieces = []
    for k in range(n):
        A, B, D = C[k - 1], C[k], C[(k + 1) % n]
        u, v = unit(A - B), unit(D - B); th = math.acos(np.clip(u @ v, -1, 1))
        r = r_tip if k % 2 == 0 else r_in
        t = r / math.tan(th / 2); s0, s1 = B + u * t, B + v * t
        h = 4 / 3 * math.tan((math.pi - th) / 4) * r
        pieces.append((s0, s0 - u * h, s1 - v * h, s1))
    pen.moveTo(tuple(pieces[0][3]))
    for k in range(1, n + 1):
        a_, b_, c_, d_ = pieces[k % n]; pen.lineTo(tuple(a_)); pen.curveTo(tuple(b_), tuple(c_), tuple(d_))
    pen.closePath(); return p
def inset(C, d):
    n = len(C); sgn = 1 if np.sum(C[:, 0] * np.roll(C[:, 1], -1) - np.roll(C[:, 0], -1) * C[:, 1]) > 0 else -1
    L = []
    for k in range(n):
        a_, b_ = C[k], C[(k + 1) % n]; t = unit(b_ - a_); L.append((a_ + np.array([-t[1], t[0]]) * sgn * d, t))
    out = []
    for k in range(n):
        (p1, t1), (p2, t2) = L[k - 1], L[k]; u_ = np.linalg.solve(np.array([t1, -t2]).T, p2 - p1); out.append(p1 + t1 * u_[0])
    return np.array(out)
for cp, filled in ((0x2605, True), (0x2606, False)):
    if cp not in cm: continue
    name = cm[cp]; C, info = star_centerline(name)
    p = filleted(C, 14, 45)
    sp = pathops.Path(); sp.addPath(p)
    sp.stroke(PEN, pathops.LineCap.ROUND_CAP, pathops.LineJoin.ROUND_JOIN, 4); sp.convertConicsToQuads()
    res = pathops.op(sp, p, pathops.PathOp.UNION)
    if not filled:
        hole = filleted(inset(C, PEN / 2), 10, 20)
        res = pathops.op(res, hole, pathops.PathOp.DIFFERENCE)
    res.simplify()
    tt = TTGlyphPen(gs); res.draw(Cu2QuPen(tt, 1.0, reverse_direction=True))
    g = tt.glyph(); g.recalcBounds(glyf); glyf[name] = g
    mono["hmtx"][name] = (mono["hmtx"][name][0], g.xMin)
# half-width katakana: the same skeletons, narrowed into the 500-wide cell, drawn with the same pen
HW_SRC = {0xFF66: 0x30F2}
HW_SRC.update(dict(zip(range(0xFF67, 0xFF70), [0x30A1, 0x30A3, 0x30A5, 0x30A7, 0x30A9, 0x30E3, 0x30E5, 0x30E7, 0x30C3])))
HW_SRC[0xFF70] = 0x30FC
HW_SRC.update(dict(zip(range(0xFF71, 0xFF9E), [ord(c) for c in "アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワン"])))
SX = 0.46
def narrow(p): return np.c_[(p[:, 0] - 500) * SX + 250, p[:, 1]]
def render(strokes, rings=(), marks=(), seed="hw"):
    p = pathops.Path(); pen = p.getPen()
    for i, s_ in enumerate(strokes):
        bz = stroke_beziers(s_, f"{seed}-{i}")
        pen.moveTo(tuple(bz[0][0]))
        for b in bz: pen.curveTo(tuple(b[1]), tuple(b[2]), tuple(b[3]))
        pen.endPath()
    for (c0, rr) in rings:
        h = 0.5523 * rr
        P = [c0 + rr * np.array(v) for v in ((1, 0), (0, 1), (-1, 0), (0, -1))]
        T = [np.array(v) for v in ((0, 1), (-1, 0), (0, -1), (1, 0))]
        pen.moveTo(tuple(P[0]))
        for q in range(4):
            a_, b_ = P[q], P[(q + 1) % 4]; pen.curveTo(tuple(a_ + T[q] * h), tuple(b_ - T[(q + 1) % 4] * h), tuple(b_))
        pen.closePath()
    p.stroke(PEN, pathops.LineCap.ROUND_CAP, pathops.LineJoin.ROUND_JOIN, 4); p.convertConicsToQuads()
    if marks:
        mp_ = pathops.Path(); mpen = mp_.getPen()
        for m in marks: mpen.moveTo(tuple(m[0])); mpen.lineTo(tuple(m[1])); mpen.endPath()
        mp_.stroke(PEN * 0.8, pathops.LineCap.ROUND_CAP, pathops.LineJoin.ROUND_JOIN, 4); mp_.convertConicsToQuads()
        p = pathops.op(p, mp_, pathops.PathOp.UNION)
    p.simplify()
    tt = TTGlyphPen(gs); p.draw(Cu2QuPen(tt, 1.0, reverse_direction=True)); return tt.glyph()
def to_mono(p): return np.c_[p[:, 0] * ax + bx, p[:, 1] * ay + by]
def add_glyph(cp_, g):
    nm = f"uni{cp_:04X}"
    if nm not in mono.getGlyphOrder():
        order = mono.getGlyphOrder(); order.append(nm); mono.setGlyphOrder(order)
    glyf[nm] = g; g.recalcBounds(glyf); mono["hmtx"][nm] = (500, getattr(g, "xMin", 0))
    for t_ in mono["cmap"].tables:
        if t_.isUnicode(): t_.cmap[cp_] = nm
HW = {}
for hw, src in HW_SRC.items():
    if src in NATIVE: st_ = [narrow(q) for q in NATIVE[src]]
    elif src in skels: st_ = [narrow(to_mono(q)) for q in skels[src]]
    else: continue
    HW[hw] = render(st_, seed=f"{hw}")
# punctuation, drawn in the half cell
L_ = lambda *pts: np.array(pts, float)
HW[0xFF61] = render([], rings=[(np.array([150.0, 70.0]), 55.0)])                       # ｡
HW[0xFF62] = render([L_((390, 760), (175, 760), (175, 400))])                           # ｢
HW[0xFF63] = render([L_((325, 340), (325, -20), (110, -20))])                           # ｣
HW[0xFF64] = render([L_((110, 150), (195, 50))])                                        # ､
HW[0xFF65] = render([L_((250, 372), (250, 388))])                                       # ･
# voiced marks: the full-width marks of ガ and the ring of パ, moved to the top of the half cell
if 0x30AC in MARKS:
    mk = [to_mono(m) for m in MARKS[0x30AC]]; c_ = np.vstack(mk).mean(0)
    HW[0xFF9E] = render([], marks=[m - c_ + np.array([230.0, 640.0]) for m in mk])      # ﾞ
if 0x30D1 in RING_OF:
    c0, rr = RING_OF[0x30D1][0]; rr = rr * (ax + ay) / 2
    HW[0xFF9F] = render([], rings=[(np.array([220.0, 640.0]), rr)])                     # ﾟ
for hw, g in HW.items(): add_glyph(hw, g)
mono.save(OUT)
print(f"{len(skels) + len(NATIVE)} kana, {len(HW)} half-width glyphs, 2 stars")

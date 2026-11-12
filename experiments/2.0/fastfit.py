"""The syllable frame fit of frames.py, with the derivatives worked out instead of
measured by nudging each number, and every stroke handled in one array.

Geometry vector g = [points (2 per point) | rings (cx, cy, rx, ry) | bends (1 per stroke)].
Every stroke is 7 points along its quadratic, every ring 24 points round it, and the
pieces are the polylines through them. Residuals:
  cover  each skeleton point to the nearest polyline,
  along  each polyline point to the nearest skeleton point given to its piece,
  prior  each point / ring held near the placement of the step before, each bend near 0.
"""
import math
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial import cKDTree

import frames as FR

NSEG = 6
NRING = 24
T = np.linspace(0, 1, NSEG + 1)
WA, WB, WC = (1 - T) ** 2, T * T, 2 * T * (1 - T)
TH = np.linspace(0, 2 * math.pi, NRING, endpoint=False)
COS, SIN = np.cos(TH), np.sin(TH)
ROT = np.array([[0.0, -1.0], [1.0, 0.0]])


class Frame:
    def __init__(self, f):
        self.s = np.array(f["s"], int).reshape(-1, 2)
        self.np_, self.nr, self.ns = len(f["p"]), len(f["r"]), len(self.s)
        self.ro = 2 * self.np_                 # where rings start in g
        self.bo = self.ro + 4 * self.nr        # where bends start in g
        self.ng = self.bo + self.ns
        nsamp = self.ns * (NSEG + 1) + self.nr * NRING
        self.nsamp = nsamp
        piece, s0, s1 = [], [], []
        for k in range(self.ns):
            base = k * (NSEG + 1)
            s0 += [base + t for t in range(NSEG)]; s1 += [base + t + 1 for t in range(NSEG)]
            piece += [k] * NSEG
        for r in range(self.nr):
            base = self.ns * (NSEG + 1) + r * NRING
            s0 += [base + t for t in range(NRING)]; s1 += [base + (t + 1) % NRING for t in range(NRING)]
            piece += [self.ns + r] * NRING
        self.seg0, self.seg1, self.seg_piece = np.array(s0), np.array(s1), np.array(piece)
        self.samp_piece = np.concatenate([np.repeat(np.arange(self.ns), NSEG + 1),
                                          np.repeat(self.ns + np.arange(self.nr), NRING)]).astype(int)
        self.npieces = self.ns + self.nr

    def g_of(self, pts, rs, bs):
        return np.concatenate([np.ravel(pts), np.ravel(rs), np.ravel(bs)])

    def split(self, g):
        return (g[:self.ro].reshape(-1, 2), g[self.ro:self.bo].reshape(-1, 4), g[self.bo:])

    def samples(self, g):
        """Polyline points S (n, 2) and dS/dg (n, 2, ng)."""
        pts, rs, bs = self.split(g)
        S = np.zeros((self.nsamp, 2)); D = np.zeros((self.nsamp, 2, self.ng))
        if self.ns:
            a, b = pts[self.s[:, 0]], pts[self.s[:, 1]]
            d = b - a
            L = np.maximum(np.hypot(d[:, 0], d[:, 1]), 1e-6)
            n = d @ ROT.T / L[:, None]                      # left normal
            c = (a + b) / 2 + 2 * bs[:, None] * n
            Sst = WA[None, :, None] * a[:, None] + WB[None, :, None] * b[:, None] + WC[None, :, None] * c[:, None]
            S[:self.ns * (NSEG + 1)] = Sst.reshape(-1, 2)
            I2 = np.eye(2)
            Mm = I2[None] / L[:, None, None] - d[:, :, None] * d[:, None, :] / L[:, None, None] ** 3
            RM = ROT[None] @ Mm
            dca = I2[None] / 2 - 2 * bs[:, None, None] * RM
            dcb = I2[None] / 2 + 2 * bs[:, None, None] * RM
            dcbeta = 2 * n
            for k in range(self.ns):
                i, j = self.s[k]
                rows = slice(k * (NSEG + 1), (k + 1) * (NSEG + 1))
                D[rows, :, 2 * i:2 * i + 2] += WA[:, None, None] * I2 + WC[:, None, None] * dca[k]
                D[rows, :, 2 * j:2 * j + 2] += WB[:, None, None] * I2 + WC[:, None, None] * dcb[k]
                D[rows, :, self.bo + k] = WC[:, None] * dcbeta[k]
        for r in range(self.nr):
            cx, cy, rx, ry = rs[r]
            rows = slice(self.ns * (NSEG + 1) + r * NRING, self.ns * (NSEG + 1) + (r + 1) * NRING)
            S[rows, 0] = cx + rx * COS; S[rows, 1] = cy + ry * SIN
            o = self.ro + 4 * r
            D[rows, 0, o] = 1; D[rows, 1, o + 1] = 1; D[rows, 0, o + 2] = COS; D[rows, 1, o + 3] = SIN
        return S, D

    def nearest_segment(self, P, S, allowed=None):
        """For each point the nearest segment, among the `allowed` ones (n, nseg) if given."""
        a0 = S[self.seg0]; ab = S[self.seg1] - a0                   # (nseg, 2)
        L2 = np.maximum((ab * ab).sum(1), 1e-9)
        t = np.clip(((P[:, None, :] - a0[None]) * ab[None]).sum(2) / L2[None], 0, 1)   # (n, nseg)
        q = a0[None] + t[..., None] * ab[None]
        dist = np.hypot(P[:, None, 0] - q[..., 0], P[:, None, 1] - q[..., 1])
        k = np.argmin(dist if allowed is None else np.where(allowed, dist, np.inf), axis=1)
        idx = np.arange(len(P))
        return k, t[idx, k], q[idx, k], dist[idx, k]


def fit_syllable(prep, parts, bends=True, frames=None):
    """prep: from prep.py. parts = [(jamo name, role, ink box)]. frames: name -> frame
    (FR.FRAMES when not given)."""
    frames = frames or FR.FRAMES
    whole = FR.F([], [], [])
    owner_p, owner_s, owner_r, units = [], [], [], []
    for n, (name, role, box) in enumerate(parts):
        g = FR.in_box(frames[name], box)
        units.append((len(whole["p"]), len(whole["p"]) + len(g["p"]), len(whole["r"]), len(whole["r"]) + len(g["r"])))
        whole = FR.join(whole, g)
        owner_p += [n] * len(g["p"]); owner_s += [n] * len(g["s"]); owner_r += [n] * len(g["r"])
    out = fit_frame(prep, whole, units, bends, boxes=[b for _, _, b in parts])
    if out:
        out.update(strokes=[tuple(s) for s in whole["s"]], owner_p=owner_p, owner_s=owner_s, owner_r=owner_r)
    return out


def fit_frame(prep, f, units, bends=True, boxes=None):
    P = prep["P"]
    if len(P) < 5:
        return None
    fr = Frame(f)
    whole_tree = cKDTree(P)
    nP = len(P)
    comp = components(prep, P)
    # the unit (jamo) of each piece, then of each segment
    unit_of = np.zeros(fr.npieces, int)
    for u, (a, z, ra, rz) in enumerate(units):
        for k, (i, j) in enumerate(fr.s):
            if a <= i < z:
                unit_of[k] = u
        unit_of[fr.ns + ra:fr.ns + rz] = u
    seg_unit = unit_of[fr.seg_piece]
    ALLOW = [None]          # which segments each skeleton point may go to, set by assign()
    inbox = None            # (n, units): the point lies in that jamo's starting box
    if boxes:
        inbox = np.column_stack([(b[0] - 30 < P[:, 0]) & (P[:, 0] < b[2] + 30) &
                                 (b[1] - 30 < P[:, 1]) & (P[:, 1] < b[3] + 30) for b in boxes])

    def resid_jac(g, trees, anchor, pw, rw, bw):
        S, D = fr.samples(g)
        k, t, q, dist = fr.nearest_segment(P, S, ALLOW[0])
        u = (q - P) / np.maximum(dist, 1e-6)[:, None]
        s0, s1 = fr.seg0[k], fr.seg1[k]
        Jc = np.einsum("nc,ncg->ng", u * (1 - t)[:, None], D[s0]) + np.einsum("nc,ncg->ng", u * t[:, None], D[s1])
        ra, Ja = [], []
        for pc in range(fr.npieces):
            rows = np.nonzero(fr.samp_piece == pc)[0]
            tree, pts = (trees[pc] if trees is not None and trees[pc] is not None else (whole_tree, P))
            dd, ii = tree.query(S[rows])
            v = (S[rows] - pts[ii]) / np.maximum(dd, 1e-6)[:, None]
            ra.append(dd); Ja.append(np.einsum("nc,ncg->ng", v, D[rows]))
        r = [dist] + ra; J = [Jc] + Ja
        # priors
        w = np.concatenate([np.full(fr.ro, pw), np.full(4 * fr.nr, rw), np.full(fr.ns, bw)])
        keep = w > 0
        r.append((w * (g - anchor))[keep]); J.append(np.diag(w)[keep])
        return np.concatenate(r), np.vstack(J), nP

    def assign(g):
        """The skeleton shared out in two levels. A piece of ink (connected) goes to the
        jamo whose starting box holds at least a fifth of its points (an initial joined
        with ㅗ goes to both); when no box does, to the jamo most of its points are nearest
        to and any other nearest to a fifth. Each point then goes to the
        nearest stroke or ring of the jamo it may go to."""
        S, _ = fr.samples(g)
        k, _, _, _ = fr.nearest_segment(P, S)
        near_unit = seg_unit[k]
        allowed_units = np.ones((nP, len(units)), bool)
        for c in np.unique(comp):
            if c == 0:
                continue
            idx = comp == c
            ok = np.zeros(len(units), bool)
            if inbox is not None:
                ok = inbox[idx].mean(axis=0) >= 0.2
            if not ok.any():
                share = np.bincount(near_unit[idx], minlength=len(units)) / idx.sum()
                ok = share >= 0.2
                ok[np.argmax(share)] = True
            allowed_units[idx] = ok
        ALLOW[0] = allowed_units[:, seg_unit]
        k, _, _, _ = fr.nearest_segment(P, S, ALLOW[0])
        own = fr.seg_piece[k]
        trees = []
        for pc in range(fr.npieces):
            q = P[own == pc]
            trees.append((cKDTree(q), q) if len(q) >= 3 else None)
        return trees

    def solve(xmap, x0, trees, anchor, pw, rw, bw, fs, nfev=100):
        """xmap: x -> (g, dg/dx)."""
        cache = {}

        def both(x):
            key = x.tobytes()
            if key not in cache:
                g, G = xmap(x)
                r, Jg, _ = resid_jac(g, trees, anchor, pw, rw, bw)
                cache.clear(); cache[key] = (r, Jg @ G)
            return cache[key]
        return least_squares(lambda x: both(x)[0], x0, jac=lambda x: both(x)[1],
                             loss="soft_l1", f_scale=fs, max_nfev=nfev).x

    pts0 = np.array(f["p"], float).reshape(-1, 2)
    rs0 = np.array(f["r"], float).reshape(-1, 4)
    g0 = fr.g_of(pts0, rs0, np.zeros(fr.ns))

    # 1. units move and scale as wholes
    centres = []
    for a, z, ra, rz in units:
        q = [pts0[a:z]] + ([rs0[ra:rz, :2]] if rz > ra else [])
        q = np.vstack([x for x in q if len(x)])
        centres.append(q.mean(axis=0))

    def affine(x):
        g = g0.copy(); G = np.zeros((fr.ng, len(x)))
        for u, (a, z, ra, rz) in enumerate(units):
            dx, dy, lx, ly = x[4 * u:4 * u + 4]
            sx, sy = math.exp(lx), math.exp(ly)
            c = centres[u]; col = 4 * u
            for p in range(a, z):
                ox, oy = pts0[p] - c
                g[2 * p] = c[0] + ox * sx + dx; g[2 * p + 1] = c[1] + oy * sy + dy
                G[2 * p, col] = 1; G[2 * p + 1, col + 1] = 1
                G[2 * p, col + 2] = ox * sx; G[2 * p + 1, col + 3] = oy * sy
            for r in range(ra, rz):
                o = fr.ro + 4 * r
                cx, cy, rx, ry = rs0[r]
                g[o] = c[0] + (cx - c[0]) * sx + dx; g[o + 1] = c[1] + (cy - c[1]) * sy + dy
                g[o + 2] = rx * sx; g[o + 3] = ry * sy
                G[o, col] = 1; G[o + 1, col + 1] = 1
                G[o, col + 2] = (cx - c[0]) * sx; G[o + 1, col + 3] = (cy - c[1]) * sy
                G[o + 2, col + 2] = rx * sx; G[o + 3, col + 3] = ry * sy
        return g, G

    x = np.zeros(4 * len(units))
    x = solve(affine, x, None, g0, 0, 0, 0, 40.0)
    assign(affine(x)[0])                     # from here on, ink pieces stay with their jamo
    x = solve(affine, x, None, g0, 0, 0, 0, 8.0)
    gA, _ = affine(x)
    ptsA, rsA, _ = fr.split(gA)
    ring_box = []
    for u, (a, z, ra, rz) in enumerate(units):
        ring_box += [boxes[u] if boxes else None] * (rz - ra)
    rsA = on_holes(prep["holes"], rsA, ring_box)
    gA = fr.g_of(ptsA, rsA, np.zeros(fr.ns))

    # 2. free points and rings, bends held at 0; 3. bends too
    nfree = fr.bo
    Gfree = np.vstack([np.eye(nfree), np.zeros((fr.ns, nfree))])
    free = lambda x: (np.concatenate([x, np.zeros(fr.ns)]), Gfree)
    full = lambda x: (x, np.eye(fr.ng))
    xf = gA[:nfree].copy()
    for _ in range(3):
        trees = assign(free(xf)[0])
        xf = solve(free, xf, trees, gA, FR.PRIOR_W, FR.RING_W, 0, 8.0)
    g = free(xf)[0]
    if bends:
        for _ in range(2):
            trees = assign(g)
            g = solve(full, g, trees, gA, FR.PRIOR_W, FR.RING_W, FR.BEND_W, 8.0)
    trees = assign(g)
    r, _, n_cover = resid_jac(g, trees, gA, 0, 0, 0)
    pts, rs, bs = fr.split(g)
    pts_l = [tuple(q) for q in pts]; rs_l = [tuple(q) for q in rs]
    bl = [float(v) for v in bs]
    return {"points": pts_l, "rings": rs_l, "bends": bl,
            "init": ([tuple(q) for q in ptsA], [tuple(q) for q in rsA]),
            "cover95": float(np.percentile(r[:n_cover], 95)),
            "along95": float(np.percentile(r[n_cover:n_cover + fr.nsamp], 95)),
            "iou": iou(prep, pts_l, f["s"], rs_l, bl)}


def components(prep, P):
    """The connected piece of ink each skeleton point lies on (0: none found)."""
    from scipy import ndimage
    off = prep["off"]; h, w = prep["shape"]
    m = np.unpackbits(prep["ink"])[:h * w].reshape(h, w).astype(bool)
    lab, _ = ndimage.label(m, structure=np.ones((3, 3)))
    r = np.clip(((off[1] - P[:, 1]) / 2).astype(int), 0, h - 1)
    c = np.clip(((P[:, 0] - off[0]) / 2).astype(int), 0, w - 1)
    return lab[r, c]


def on_holes(holes, rs, boxes=None):
    """Each ring starts on a hole: the nearest unused one whose centre lies within the
    ring's jamo box (grown by a quarter), or else within 1.5 radii of the ring."""
    rs = rs.copy(); used = set()
    for k, (cx, cy, rx, ry) in enumerate(rs):
        best = None
        for h, (hx, hy, hw, hh) in enumerate(holes):
            if h in used:
                continue
            u = np.hypot((hx - cx) / (1.5 * max(abs(rx), 20)), (hy - cy) / (1.5 * max(abs(ry), 20)))
            ok = u < 1
            if boxes and boxes[k] is not None:
                x0, y0, x1, y1 = boxes[k]
                gx, gy = (x1 - x0) / 4, (y1 - y0) / 4
                ok = ok or (x0 - gx < hx < x1 + gx and y0 - gy < hy < y1 + gy)
            if ok and (best is None or u < best[0]):
                best = (u, h)
        if best:
            hx, hy, hw, hh = holes[best[1]]
            rs[k] = (hx, hy, hw + FR.PEN / 2, hh + FR.PEN / 2)
            used.add(best[1])
    return rs


def iou(prep, pts, strokes, rs, bends):
    """IoU at half resolution against the ink."""
    off = prep["off"]; h, w = prep["shape"]
    m = np.unpackbits(prep["ink"])[:h * w].reshape(h, w).astype(bool)
    half = lambda p: (off[0] + (p[0] - off[0]) / 2, off[1] - (off[1] - p[1]) / 2)
    drawn = FR.draw([half(p) for p in pts], [tuple(s) for s in strokes],
                    [(*half((cx, cy)), rx / 2, ry / 2) for cx, cy, rx, ry in rs],
                    (h, w), off, width=FR.PEN / 2, bends=[b / 2 for b in bends])
    return float((m & drawn).sum() / max(1, (m | drawn).sum()))

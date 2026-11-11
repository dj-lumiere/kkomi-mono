"""ㅎ as three strokes (tick, bar, ring) measured in every syllable the designer drew."""
import sys, collections
import numpy as np
sys.path.insert(0, "/home/lumi/programming/RiderProjects/LumiFoundry/fonts/kkomi-mono/tools")
import make_mono as M, hangul_fill as H

def area(q):
    return M.signed_area(M.polygon_points(q)[0])

def inside(a, b, m=2):
    return a[0] >= b[0] - m and a[1] >= b[1] - m and a[2] <= b[2] + m and a[3] <= b[3] + m

def rings(cs):
    """(outer, [holes]) for contours holding a hole."""
    out = []
    for q in cs:
        bq = M.bounds(q)
        holes = [h for h in cs if h is not q and area(h) * area(q) < 0 and inside(M.bounds(h), bq)]
        if holes:
            out.append((q, holes))
    return out

def h_strokes(cs):
    """{'ring': contours, 'bar': contours, 'tick': contours, 'merged': bool} or None."""
    rs = rings(cs)
    if not rs:
        return None
    outer, holes = max(rs, key=lambda r: M.bounds(r[0])[3])
    rb = M.bounds(outer)
    above = [q for q in cs if q is not outer and not any(q is h for h in holes)
             and M.bounds(q)[1] >= rb[3] - 35
             and M.bounds(q)[0] < rb[2] and M.bounds(q)[2] > rb[0]]
    if not above:
        return None
    above.sort(key=lambda q: M.bounds(q)[1])
    if len(above) == 1:
        return {"ring": [outer] + holes, "bar": above, "tick": [], "merged": True}
    return {"ring": [outer] + holes, "bar": [above[0]], "tick": above[1:2], "merged": False}

def ring_box(ring):
    """The ring's box. When the ring is drawn in one with the ㅗ under it, only the part
    above the hole's bottom less one stroke counts."""
    outer, holes = ring[0], ring[1:]
    hb = M.bounds(H.flatten(holes)); ob = M.bounds(outer)
    thick = ob[3] - hb[3]
    if hb[1] - ob[1] < 1.6 * thick:
        return ob
    pts = [p for poly in M.polygon_points(M.flattened(outer)) for p in poly if p[1] >= hb[1] - thick]
    xs = [p[0] for p in pts]
    return (min(xs), hb[1] - thick, max(xs), ob[3])

def measure(st):
    r = ring_box(st["ring"])
    b = M.bounds(H.flatten(st["bar"]))
    if st["merged"]:
        t_top = b[3]; bar_top = b[3]
        t = None
    else:
        t = M.bounds(H.flatten(st["tick"])); t_top = t[3]
    return {"ring_w": r[2] - r[0], "ring_h": r[3] - r[1], "ring_cx": (r[0] + r[2]) / 2, "ring_bot": r[1],
            "bar_l": b[0], "bar_r": b[2], "bar_y": b[1], "tick_top": t_top,
            "tick_len": (t[3] - t[1]) if t else None}

if __name__ == "__main__":
    import pickle
    from fontTools.ttLib import TTFont
    tt = TTFont(sys.argv[1]); gs, cmap = tt.getGlyphSet(), tt.getBestCmap()
    data = {}
    bad = []
    for cp in range(H.BASE, H.BASE + 11172):
        if H.decompose(cp)[0] != 18 or cp not in cmap:
            continue
        ops = M.record(gs, cmap[cp])
        if M.bounds(ops) is None:
            continue
        st = h_strokes(M.polygon_points_ops(ops))
        if st is None:
            bad.append(chr(cp)); continue
        data[cp] = (st, measure(st))
    print("measured", len(data), "failed", "".join(bad))
    print("merged tick+bar", sum(d[0]["merged"] for d in data.values()))
    keys = ["ring_w", "ring_h", "ring_cx", "ring_bot", "bar_l", "bar_r", "bar_y", "tick_top"]
    # additive model: value = vowel effect + final effect (none / with)
    rows = list(data.items())
    X = np.zeros((len(rows), 22))
    for n, (cp, _) in enumerate(rows):
        i, v, f = H.decompose(cp); X[n, v] = 1; X[n, 21] = 1 if f else 0
    for k in keys:
        y = np.array([d[1][k] for _, d in rows])
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        pred = X @ coef
        r2 = 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()
        print(f"{k:9s} mean {y.mean():6.0f} sd {y.std():5.1f}  R2 {r2:.2f}  resid sd {(y-pred).std():5.1f}  final effect {coef[21]:+.0f}")
    for ch in "하호회화효혜히흐희흑흙":
        cp = ord(ch)
        if cp in data:
            print(ch, {k: round(v) if v is not None else None for k, v in data[cp][1].items()})
    pickle.dump({cp: d[1] for cp, d in data.items()}, open("h_meas.pkl", "wb"))

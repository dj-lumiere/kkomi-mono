"""One bend number per stroke against two: each syllable is fitted from 4 starting boxes
(its own, and 3 shifted at random by up to 30 units and scaled by up to 6%). Reports how
well the fits hold (cover95, along95, IoU) and how much the fitted numbers move between
starts (point spread in units, bend spread in units).
usage: FRAME_BENDS=1|2 stab.py split_all.pkl fits.pkl(for the syllable list) n [learned fits]"""
import sys, pickle, collections
import numpy as np
from multiprocessing import Pool

src, listing, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
sys.argv = ["syl_fit.py", src, "1", "unused.pkl"] + sys.argv[4:5]
exec(open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "syl_fit.py")).read().split("if __name__")[0])


def run(cp):
    tt = TTFont(SRC); gs, cmap = tt.getGlyphSet(), tt.getBestCmap()
    i, v, f = H.decompose(cp); hf = bool(f); vc = H.vowel_class(v)
    single = H.DOUBLE_OF.get(i, i)
    own = cap["sp"].get(cp) or (None, None, None)
    ob = lambda c: M.bounds(H.flatten(cs(c))) if c else None
    base = [(I[i], "초성", ob(own[0]) or box(("I", i, v, hf), ("I", i, vc, hf), ("I", single, v, hf),
                                           ("I", single, vc, hf), ("I*", vc, hf))),
            (V[v], "중성", ob(own[1]) or box(("V", v, hf), ("V", v, not hf)))]
    if f:
        base.append((F[f], "종성", ob(own[2]) or box(("F", f, v), ("F", f, vc), ("F*", vc))))
    contours = M.polygon_points_ops(M.record(gs, cmap[cp]))
    rng = np.random.default_rng(cp)
    outs = []
    for t in range(4):
        parts = []
        for name, role, b in base:
            if t:
                cx, cy = (b[0] + b[2]) / 2 + rng.uniform(-30, 30), (b[1] + b[3]) / 2 + rng.uniform(-30, 30)
                s = 1 + rng.uniform(-.06, .06)
                hw, hh = s * (b[2] - b[0]) / 2, s * (b[3] - b[1]) / 2
                b = (cx - hw, cy - hh, cx + hw, cy + hh)
            parts.append((name, role, b))
        try:
            outs.append(FR.fit_syllable(contours, parts))
        except Exception:
            outs.append(None)
    return cp, outs


if __name__ == "__main__":
    prev = pickle.load(open(listing, "rb"))
    cps = sorted(cp for cp, r in prev.items() if FR.good(r))[:n]
    with Pool(6) as pool:
        res = dict(pool.imap_unordered(run, cps))
    cov, alo, iou, ok, psd, bsd, bmag = [], [], [], [], [], [], []
    for cp, outs in res.items():
        outs = [o for o in outs if o]
        if len(outs) < 2:
            continue
        cov += [o["cover95"] for o in outs]; alo += [o["along95"] for o in outs]
        iou += [o["iou"] for o in outs]; ok += [FR.good(o) for o in outs]
        P = np.array([o["points"] for o in outs])          # runs x points x 2
        psd.append(float(np.mean(np.hypot(*P.std(axis=0).T))))
        B = np.array([np.reshape(o["bends"], -1) for o in outs])
        bsd.append(float(np.mean(B.std(axis=0))))
        bmag.append(float(np.mean(np.abs(B))))
    print(f"bends per stroke {FR.NB}: {len(res)} syllables x 4 starts")
    print(f"  holds {np.mean(ok):.2f}  cover95 {np.median(cov):.1f}  along95 {np.median(alo):.1f}  IoU {np.median(iou):.3f}")
    print(f"  spread between starts: points {np.median(psd):.1f} units, bends {np.median(bsd):.1f} units"
          f"  (bend size {np.median(bmag):.1f})")

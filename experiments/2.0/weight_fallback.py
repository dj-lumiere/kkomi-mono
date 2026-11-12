"""How many of the 11,172 modern syllables would close up at 800 and 900 (pieces drawn
apart at Regular coming closer than 29 units), from their fitted centrelines."""
import os
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
import pickle, numpy as np
from multiprocessing import Pool
import frames as FR
FT = pickle.load(open("audit_fits2.pkl", "rb"))
TOUCH, LEAST = 74, 29
PENS = {700: 64 * 112 / 82, 800: 64 * 130 / 82, 900: 64 * 150 / 82}


def tightest(cp):
    r = FT[cp]
    if not r or "strokes" not in r:
        return cp, None
    ps = []
    for k, (a, b) in enumerate(r["strokes"]):
        ps.append((np.asarray(FR.curve(r["points"][a], r["points"][b], r["bends"][k], n=16)), {a, b}))
    for cx, cy, rx, ry in r["rings"]:
        t = np.linspace(0, 2 * np.pi, 32)
        ps.append((np.column_stack([cx + abs(rx) * np.cos(t), cy + abs(ry) * np.sin(t)]), set()))
    m = 1e9
    for x in range(len(ps)):
        for y in range(x + 1, len(ps)):
            if ps[x][1] & ps[y][1]:
                continue
            A, B = ps[x][0], ps[y][0]
            d = np.hypot(A[:, None, 0] - B[None, :, 0], A[:, None, 1] - B[None, :, 1]).min()
            if d >= TOUCH:
                m = min(m, d)
    return cp, m


if __name__ == "__main__":
    with Pool(6) as pool:
        res = dict(pool.map(tightest, sorted(FT), chunksize=64))
    ds = np.array([v for v in res.values() if v is not None])
    for w, pen in PENS.items():
        bad = (ds < pen + LEAST).sum()
        print(f"{w}: {bad} of {len(ds)} syllables would close up ({bad / len(ds):.0%})")
    order = sorted((v, chr(cp)) for cp, v in res.items() if v is not None)
    print("tightest:", "".join(c for _, c in order[:30]), " loosest:", "".join(c for _, c in order[-30:]))

"""Where Hangul gets tight, and what a flat pen buys. For every syllable, the closest pair
of pieces kept apart at Regular: is the gap up-down or sideways? Then, at 700/800/900,
how many syllables close up with a round pen and with flat pens (flat strokes 0.85 or
0.7 of upright ones): two pens of half-widths a (across) and b (up) need, along the gap's
direction u, 2 * sqrt((a ux)^2 + (b uy)^2) plus 29 units of white."""
import os
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
import pickle, numpy as np
from multiprocessing import Pool
import frames as FR
FT = pickle.load(open("audit_fits2.pkl", "rb"))
TOUCH, LEAST = 74, 29
STEMS = {700: 112, 800: 130, 900: 150}
RATIOS = [1.0, 0.85, 0.7]


def gaps(cp):
    """All gaps between pieces kept apart at Regular: (distance, ux, uy)."""
    r = FT[cp]
    if not r or "strokes" not in r:
        return cp, []
    ps = []
    for k, (a, b) in enumerate(r["strokes"]):
        ps.append((np.asarray(FR.curve(r["points"][a], r["points"][b], r["bends"][k], n=16)), {a, b}))
    for cx, cy, rx, ry in r["rings"]:
        t = np.linspace(0, 2 * np.pi, 32)
        ps.append((np.column_stack([cx + abs(rx) * np.cos(t), cy + abs(ry) * np.sin(t)]), set()))
    out = []
    for x in range(len(ps)):
        for y in range(x + 1, len(ps)):
            if ps[x][1] & ps[y][1]:
                continue
            A, B = ps[x][0], ps[y][0]
            D = np.hypot(A[:, None, 0] - B[None, :, 0], A[:, None, 1] - B[None, :, 1])
            i, j = np.unravel_index(D.argmin(), D.shape)
            d = D[i, j]
            if d >= TOUCH:
                v = (B[j] - A[i]) / d
                out.append((d, abs(v[0]), abs(v[1])))
    return cp, out


if __name__ == "__main__":
    with Pool(6) as pool:
        res = dict(pool.map(gaps, sorted(FT), chunksize=64))
    tight = [min(g) for g in res.values() if g]
    up = sum(uy > ux for _, ux, uy in tight)
    print(f"closest gap per syllable: up-down {up} ({up / len(tight):.0%}), sideways {len(tight) - up}")
    for w, st in STEMS.items():
        line = []
        for ratio in RATIOS:
            a = 64 * st / 82 / 2; b = a * ratio
            bad = sum(any(d < 2 * np.hypot(a * ux, b * uy) + LEAST for d, ux, uy in g) for g in res.values() if g)
            line.append(f"flat {ratio:.2f}: {bad / len(res):.0%}")
        print(w, "  ".join(line))

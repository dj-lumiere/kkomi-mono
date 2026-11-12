"""syl_fit.py on fastfit: same starting boxes and learning, prep.pkl instead of the font.
usage: fast_run.py split_all.pkl prep.pkl (step | chars) out.pkl [previous fits to learn from]"""
import os
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")      # six workers, one thread each
import sys, pickle, time, collections
from multiprocessing import Pool
import numpy as np
SPLIT, PREP, ARG, OUT = sys.argv[1:5]
sys.argv = ["syl_fit.py", SPLIT, "1", OUT] + sys.argv[5:6]
exec(open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "syl_fit.py")).read().split("def " + "job(cp):")[0])
import fastfit as FF
PR = pickle.load(open(PREP, "rb"))


def near(a, b, least=0.5):
    """Two boxes overlap by at least `least` of their union."""
    w = min(a[2], b[2]) - max(a[0], b[0]); h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return False
    inter = w * h
    area = lambda q: (q[2] - q[0]) * (q[3] - q[1])
    return inter / (area(a) + area(b) - inter) >= least


def parts_of(cp):
    """Starting boxes. A syllable's own split is used only where it is sound: never for a
    double initial (the split gives its second half to the vowel), and not when the initial
    and the vowel are joined (the split leaves ㅗ with the initial)."""
    i, v, f = H.decompose(cp); hf = bool(f); vc = H.vowel_class(v)
    single = H.DOUBLE_OF.get(i, i)
    own = cap["sp"].get(cp) or (None, None, None)
    ob = lambda c: M.bounds(H.flatten(cs(c))) if c else None
    trust = bool(own[0]) and bool(own[1]) and i not in H.DOUBLE_OF and CO.sound(cs(own[0]), cs(own[1]), v)
    vref = box(("V", v, hf, "I", i), ("V", v, hf, i in H.DOUBLE_OF), ("V", v, hf), ("V", v, not hf))
    iref = box(("I", i, v, hf), ("I", i, vc, hf))
    fref = box(("F", f, v, "I", i), ("F", f, v), ("F", f, vc), ("F*", vc)) if f else None
    if trust:   # a sound split can still be wrong: its boxes must look like the usual ones
        trust = all(near(ob(c), ref) for c, ref in ((own[0], iref), (own[1], vref), (own[2], fref)) if c and ref)
    vbox = (trust and ob(own[1])) or vref
    ibox = (trust and ob(own[0])) or iref
    if ibox is None:
        ibox = box(("I", single, v, hf), ("I", single, vc, hf), ("I*", vc, hf))
        if i in H.DOUBLE_OF:          # two of the single side by side, up to the vowel
            x0, y0, x1, y1 = ibox
            right = x0 + 1.8 * (x1 - x0)
            if vbox[0] > x0 + 0.5 * (x1 - x0):
                right = min(right, vbox[0] - 30)
            ibox = (x0, y0, max(right, x1), y1)
    parts = [(I[i], "초성", ibox), (V[v], "중성", vbox)]
    if f:
        parts.append((F[f], "종성", (trust and ob(own[2])) or fref))
    return parts


def score(r):
    return r["cover95"] + r["along95"] if r and "cover95" in r else 1e9


def job(cp):
    """One fit; when it fails, more starts (the hand-made frames, and boxes moved at
    random by up to 40 units) and the best of them."""
    try:
        parts = parts_of(cp)
        best = FF.fit_syllable(PR[cp], parts)
        if FR.good(best):
            return cp, best
        r = FF.fit_syllable(PR[cp], parts, match=False)     # without the line matching
        if score(r) < score(best):
            best = r
        if FR.good(best):
            best["tries"] = True
            return cp, best
        rng = np.random.default_rng(cp)
        tries = [(parts, FR.TEMPLATE)]
        for _ in range(4):
            tries.append(([(n, ro, tuple(np.array(b) + np.repeat(rng.uniform(-40, 40, 2), 2) * (1, 1, 1, 1)
                                         + rng.uniform(-15, 15, 4)))
                           for n, ro, b in parts], None))
        for p, frames in tries:
            r = FF.fit_syllable(PR[cp], p, frames=frames)
            if score(r) < score(best):
                best = r
            if FR.good(best):
                break
        best["tries"] = True
        return cp, best
    except Exception as e:
        return cp, {"error": repr(e)}


if __name__ == "__main__":
    cps = sorted(k for k in PR if isinstance(k, int))
    cps = cps[::int(ARG)] if ARG.isdigit() else [ord(c) for c in ARG if ord(c) in PR]
    t0 = time.time()
    with Pool(6) as pool:
        res = dict(pool.imap_unordered(job, cps, chunksize=2))
    print(f"{len(res)} syllables in {time.time() - t0:.1f}s")
    good = FR.good
    ok = sum(good(r) for r in res.values())
    print(f"fit {ok}/{len(res)} = {ok/len(res):.2f}  IoU median {np.median([r['iou'] for r in res.values() if r and 'iou' in r]):.3f}")
    for role_idx, names in ((0, I), (1, V)):
        by = collections.defaultdict(list)
        for cp, r in res.items():
            by[names[H.decompose(cp)[role_idx]]].append(good(r))
        print("by", "초성" if role_idx == 0 else "중성", sorted(((round(sum(x)/len(x), 2), k, len(x)) for k, x in by.items()))[:8])
    print("errors", [r["error"] for r in res.values() if r and "error" in r][:3])
    pickle.dump(res, open(OUT, "wb"))

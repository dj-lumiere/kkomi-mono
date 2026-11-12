"""All 11,172 modern syllables composed from the designer's own jamo (exemplar.py), the layout
rules, one pen), checked against limits read off the designer's drawn syllables:

  cell     ink beyond where any drawn syllable puts it
  white    two jamo closer than the drawn ever put them (per pair and vowel class)
  narrow   ink narrower than 500 units (the build cannot widen it to fill the cell)
  far      (drawn syllables only) the composed centrelines lie far from the designer's
           own (mean distance both ways), i.e. the reinterpretation strays from the drawing

usage: audit2.py audit_rec.pkl audit_fits2.pkl out_prefix"""
import os
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
import sys, pickle, json, collections
import numpy as np
from multiprocessing import Pool

REC, FITS, PREFIX = sys.argv[1:4]
sys.argv = ["compose_old.py", "split_all.pkl", "prep2.pkl", "fit_r3.pkl", "unused.png"]
exec(open("compose_old.py").read().replace("\nmain()\n", "\n"))
import exemplar as EX
_PRA = pickle.load(open("audit_prep.pkl", "rb"))
EXS = EX.Exemplars(pickle.load(open(FITS, "rb")), _PRA["_drawn"], box)

FT = pickle.load(open(FITS, "rb"))
DOT = 0.8


def pieces_of(parts):
    """[(points, kind, role)] of a laid-out syllable, with ROLES as syllable() left them."""
    out = []
    for part, role in zip(parts, ROLES):
        if part[0] == "dot":
            b = part[1]
            out.append((np.array([((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)]), "dot", role)); continue
        frame, b = part
        g = FR.in_box(frame, b)
        bs = frame.get("b", [0] * len(g["s"]))
        size = max(b[2] - b[0] - PEN, b[3] - b[1] - PEN)
        for kk, (i, j) in enumerate(g["s"]):
            out.append((np.asarray(FR.curve(g["p"][i], g["p"][j], bs[kk] * size if kk < len(bs) else 0, n=16)), "stroke", role))
        for cx, cy, rx, ry in g["r"]:
            a = np.linspace(0, 2 * np.pi, 32)
            out.append((np.column_stack([cx + abs(rx) * np.cos(a), cy + abs(ry) * np.sin(a)]), "ring", role))
    return out


def half(kind):
    return DOT * PEN if kind == "dot" else PEN / 2


def designer_points(cp):
    r = FT.get(cp)
    if not r or "strokes" not in r:
        return None
    pts = [np.asarray(FR.curve(r["points"][i], r["points"][j], r["bends"][k], n=16)) for k, (i, j) in enumerate(r["strokes"])]
    for cx, cy, rx, ry in r["rings"]:
        a = np.linspace(0, 2 * np.pi, 32)
        pts.append(np.column_stack([cx + abs(rx) * np.cos(a), cy + abs(ry) * np.sin(a)]))
    return np.vstack(pts)


def one(cp):
    i, v, f = H.decompose(cp)
    text = I[i] + V[v] + (F[f] if f else "")
    try:
        ex = EXS.parts_for(cp)
        parts = [(fr, b) for fr, b, _ in ex]
        ROLES[:] = [r for _, _, r in ex]
    except Exception as e:
        return cp, {"error": repr(e)}
    ps = pieces_of(parts)
    allp = np.vstack([p[0] for p in ps])
    pad = max(half(p[1]) for p in ps)
    b = (allp[:, 0].min() - PEN / 2, allp[:, 1].min() - PEN / 2, allp[:, 0].max() + PEN / 2, allp[:, 1].max() + PEN / 2)
    whites = {}
    for x in range(len(ps)):
        for y in range(x + 1, len(ps)):
            ra, rb = ps[x][2], ps[y][2]
            if ra == rb:
                continue
            A, B = ps[x][0], ps[y][0]
            d = np.hypot(A[:, None, 0] - B[None, :, 0], A[:, None, 1] - B[None, :, 1]).min() - half(ps[x][1]) - half(ps[y][1])
            key = "".join(sorted({ra, rb}, key="IVF".index))
            whites[key] = min(whites.get(key, 1e9), float(d))
    far = None
    D = designer_points(cp)
    if D is not None:
        A = allp
        dd = np.hypot(A[:, None, 0] - D[None, :, 0], A[:, None, 1] - D[None, :, 1])
        far = float((dd.min(axis=1).mean() + dd.min(axis=0).mean()) / 2)
    return cp, {"bounds": b, "whites": whites, "far": far}


def main():
    rec = pickle.load(open(REC, "rb"))
    drawn = {cp for cp, d in rec.items() if d["drawn"]}
    D = [d for d in rec.values() if d["drawn"]]
    bb = np.array([d["bounds"] for d in D])
    lim = {"x0": bb[:, 0].min() - 10, "y0": bb[:, 1].min() - 10, "x1": bb[:, 2].max() + 10, "y1": bb[:, 3].max() + 10}
    wl = collections.defaultdict(list)
    for d in D:
        if d["fit"]:
            for k, w in d["whites"].items():
                wl[(k, H.vowel_class(d["v"]))].append(w)
    wlim = {k: float(np.percentile(v, 0.5)) for k, v in wl.items() if len(v) >= 20}

    with Pool(6) as pool:
        res = dict(pool.imap_unordered(one, range(H.BASE, H.BASE + 11172), chunksize=32))
    errors = [chr(cp) for cp, r in res.items() if "error" in r]
    flags = {}
    for cp, r in res.items():
        if "error" in r:
            continue
        fl = []
        b = r["bounds"]
        if b[0] < lim["x0"] or b[1] < lim["y0"] or b[2] > lim["x1"] or b[3] > lim["y1"]:
            fl.append("cell")
        vc = H.vowel_class(H.decompose(cp)[1])
        if any(w < wlim.get((k, vc), -1e9) - 10 for k, w in r["whites"].items()):
            fl.append("white")
        if b[2] - b[0] < 500:
            fl.append("narrow")
        flags[cp] = fl
    fars = np.array([r["far"] for cp, r in res.items() if cp in drawn and r.get("far") is not None])
    far_lim = 40.0
    for cp, r in res.items():
        if cp in drawn and r.get("far") is not None and r["far"] > far_lim:
            flags[cp].append("far")
    n = len(res)
    print(f"composed {n - len(errors)} of {n}; errors {len(errors)} {''.join(errors[:20])}")
    for c in ["cell", "white", "narrow"]:
        k = sum(c in f for f in flags.values())
        print(f"  {c:7} {k:5} ({k / n:.1%})")
    print(f"  far     drawn {len(fars)}: mean distance to the designer's centrelines median {np.median(fars):.0f}, p90 {np.percentile(fars, 90):.0f}, max {fars.max():.0f}; over {far_lim:.0f}: {(fars > far_lim).sum()}")
    k = sum(bool(f) for f in flags.values())
    print(f"  any     {k:5} ({k / n:.1%})")
    json.dump({"flags": {chr(cp): f for cp, f in flags.items() if f}, "errors": errors, "drawn": [chr(c) for c in drawn],
               "far": {chr(cp): r["far"] for cp, r in res.items() if r.get("far") is not None}},
              open(PREFIX + ".json", "w"), ensure_ascii=False)


if __name__ == "__main__":
    main()

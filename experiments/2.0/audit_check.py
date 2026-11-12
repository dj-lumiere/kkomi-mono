"""Checks the 11,172 modern syllables of the current build against what the designer did.
Every limit comes from the designer's own 2,809 drawn syllables; each check reports how
many of those it flags too (its false alarms) and how many built ones.

  fit      the syllable's jamo frames do not fit its skeleton (a stroke missing, extra,
           or run together with another)
  holes    a closed white (ㅇ ㅁ ㅂ ...) count differs from what its jamo give (learned
           from the drawn: holes = initial's + vowel's + final's)
  cell     ink beyond where any drawn syllable puts it
  blob     a stroke thicker than the drawn ever are (strokes piled on each other)
  white    the white between two jamo narrower than the drawn ever leave (per pair: initial
           and vowel, initial and final, vowel and final)
  narrow   the build widens each syllable to 0.8 of its two cells but at most 1.6 times, so
           ink narrower than 500 units stays narrow in the monospaced font
  hgap     the widest band with no ink from top to bottom between the ink's two sides
           (white between jamo), times the build's widening, wider than in 99.5% of the drawn

usage: audit_check.py audit_prep.pkl audit_fits.pkl out_prefix"""
import sys, pickle, collections, json
import numpy as np
from scipy import ndimage
import frames as FR, hangul_fill as H

I = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"; V = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
F = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"


def thickest(p):
    h, w = p["shape"]
    m = np.unpackbits(p["ink"])[:h * w].reshape(h, w).astype(bool)
    return float(2 * 2 * ndimage.distance_transform_edt(m).max())       # half resolution


CELL = (13, -153, 844, 819)      # where 98% of the drawn syllables put their ink


WIDE = 1000                      # the build's two cells, in source units (upm 1000)


def widening(width):
    """How much the build widens a syllable whose ink is `width` wide (enlarge_hangul)."""
    return min(1.6, max(1.04, 0.8 * WIDE / max(width, 1)))


def widest_inner_band(p):
    """Width in units of the widest run of columns with no ink, between the ink's leftmost
    and rightmost columns."""
    h, w = p["shape"]
    m = np.unpackbits(p["ink"])[:h * w].reshape(h, w).astype(bool)
    inked = np.nonzero(m.any(axis=0))[0]
    if len(inked) < 2:
        return 0.0
    cols = m.any(axis=0)[inked[0]:inked[-1] + 1]
    best = run = 0
    for v in cols:
        run = 0 if v else run + 1
        best = max(best, run)
    return float(2 * best)


def unit_samples(r):
    out = collections.defaultdict(list)
    for k, (i, j) in enumerate(r["strokes"]):
        out[r["owner_s"][k]].append(FR.curve(r["points"][i], r["points"][j], r["bends"][k], n=12))
    for k, (cx, cy, rx, ry) in enumerate(r["rings"]):
        a = np.linspace(0, 2 * np.pi, 32, endpoint=False)
        out[r["owner_r"][k]].append(np.column_stack([cx + rx * np.cos(a), cy + ry * np.sin(a)]))
    return {u: np.vstack(v) for u, v in out.items()}


def whites(r):
    """White between each pair of jamo: least centreline distance less one pen."""
    us = unit_samples(r)
    out = {}
    names = {0: "I", 1: "V", 2: "F"}
    for a in us:
        for b in us:
            if a < b:
                A, B = us[a], us[b]
                d = np.hypot(A[:, None, 0] - B[None, :, 0], A[:, None, 1] - B[None, :, 1]).min()
                out[names[a] + names[b]] = float(d - FR.PEN)
    return out


def main(prep_path, fit_path, prefix):
    PR = pickle.load(open(prep_path, "rb")); drawn = PR.pop("_drawn")
    FITS = pickle.load(open(fit_path, "rb"))
    cps = sorted(PR)
    rec = {}
    for cp in cps:
        p, r = PR[cp], FITS.get(cp)
        i, v, f = H.decompose(cp)
        rec[cp] = {"i": i, "v": v, "f": f, "drawn": cp in drawn, "holes": len(p["holes"]),
                   "bounds": tuple(p["bounds"]), "thick": thickest(p), "fit": FR.good(r),
                   "band": widest_inner_band(p) * widening(p["bounds"][2] - p["bounds"][0]),
                   "whites": whites(r) if r and "strokes" in r else {}}
    D = [rec[cp] for cp in cps if rec[cp]["drawn"]]

    # holes: least squares on the drawn, per jamo, rounded
    nI, nV, nF = len(I), len(V), len(F)
    X = np.zeros((len(D), nI + nV + nF)); y = np.array([d["holes"] for d in D], float)
    for n, d in enumerate(D):
        X[n, d["i"]] = 1; X[n, nI + d["v"]] = 1; X[n, nI + nV + d["f"]] = 1
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    pred = lambda d: int(round(coef[d["i"]] + coef[nI + d["v"]] + coef[nI + nV + d["f"]]))
    # limits from the drawn
    b = np.array([d["bounds"] for d in D])
    lim = {"x0": b[:, 0].min() - 10, "y0": b[:, 1].min() - 10, "x1": b[:, 2].max() + 10, "y1": b[:, 3].max() + 10,
           "thick": float(np.percentile([d["thick"] for d in D], 99.9)) + 4,
           "w": 0.8 * WIDE / 1.6,
           "band": float(np.percentile([d["band"] for d in D], 99.5))}
    wl = collections.defaultdict(list)
    for d in D:
        if d["fit"]:
            for k, w in d["whites"].items():
                wl[(k, H.vowel_class(d["v"]))].append(w)
    wlim = {k: float(np.percentile(v, 0.5)) for k, v in wl.items() if len(v) >= 20}

    flags = {}
    for cp in cps:
        d = rec[cp]; fl = []
        if not d["fit"]:
            fl.append("fit")
        if d["holes"] != pred(d):
            fl.append("holes")
        bx = d["bounds"]
        if bx[0] < lim["x0"] or bx[1] < lim["y0"] or bx[2] > lim["x1"] or bx[3] > lim["y1"]:
            fl.append("cell")
        if d["thick"] > lim["thick"]:
            fl.append("blob")
        if bx[2] - bx[0] < lim["w"]:
            fl.append("narrow")
        if d["band"] > lim["band"]:
            fl.append("hgap")
        for k, w in d["whites"].items():
            t = wlim.get((k, H.vowel_class(d["v"])))
            if t is not None and w < t - 10:
                fl.append("white"); break
        flags[cp] = fl

    checks = ["fit", "holes", "cell", "blob", "white", "narrow", "hgap"]
    summary = {}
    for c in checks:
        nd = sum(c in flags[cp] for cp in cps if rec[cp]["drawn"])
        nb = sum(c in flags[cp] for cp in cps if not rec[cp]["drawn"])
        summary[c] = (nd, nb)
    nd_any = sum(bool(flags[cp]) for cp in cps if rec[cp]["drawn"])
    nb_any = sum(bool(flags[cp]) for cp in cps if not rec[cp]["drawn"])
    n_d = sum(rec[cp]["drawn"] for cp in cps); n_b = len(cps) - n_d
    print(f"drawn {n_d}, built {n_b}")
    for c in checks:
        print(f"  {c:6} drawn {summary[c][0]:5} ({summary[c][0] / n_d:.1%})   built {summary[c][1]:5} ({summary[c][1] / n_b:.1%})")
    print(f"  any    drawn {nd_any:5} ({nd_any / n_d:.1%})   built {nb_any:5} ({nb_any / n_b:.1%})")
    print("limits", {k: round(v) for k, v in lim.items()}, "hole coef", {I[k]: round(coef[k], 2) for k in range(nI) if abs(coef[k]) > .3})
    json.dump({"summary": summary, "flags": {chr(cp): flags[cp] for cp in cps if flags[cp]},
               "drawn": [chr(cp) for cp in cps if rec[cp]["drawn"]]},
              open(prefix + ".json", "w"), ensure_ascii=False)
    pickle.dump(rec, open(prefix + "_rec.pkl", "wb"))


if __name__ == "__main__":
    main(*sys.argv[1:4])

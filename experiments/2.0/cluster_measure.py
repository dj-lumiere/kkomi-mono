"""How a cluster of two jamo sits, read from the frame fits.

For every well fitted syllable with a two-jamo initial (ㄲ ㄸ ㅃ ㅆ ㅉ) or final (ㄲ ㅆ and
the mixed ㄳ ㄵ ... ㅄ), each component's box (its centrelines grown by half the pen) is
compared with the box the single jamo has in the same place (same vowel, same final or
not), taken as the median over well fitted syllables with that single jamo.
usage: cluster_measure.py fits.pkl"""
import sys, pickle, collections
import numpy as np
import frames as FR, hangul_fill as H

I = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"; V = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
F = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"
PAIR = {"ㄲ": "ㄱㄱ", "ㄸ": "ㄷㄷ", "ㅃ": "ㅂㅂ", "ㅆ": "ㅅㅅ", "ㅉ": "ㅈㅈ", "ㄳ": "ㄱㅅ", "ㄵ": "ㄴㅈ",
        "ㄶ": "ㄴㅎ", "ㄺ": "ㄹㄱ", "ㄻ": "ㄹㅁ", "ㄼ": "ㄹㅂ", "ㄽ": "ㄹㅅ", "ㄾ": "ㄹㅌ", "ㄿ": "ㄹㅍ",
        "ㅀ": "ㄹㅎ", "ㅄ": "ㅂㅅ"}
P2 = FR.PEN / 2


def unit_parts(r, n):
    """Point and ring lists of unit n of a fit."""
    ss = [s for s, o in zip(r["strokes"], r["owner_s"]) if o == n]
    ids = sorted({i for s in ss for i in s})
    rs = [q for q, o in zip(r["rings"], r["owner_r"]) if o == n]
    return [r["points"][i] for i in ids], rs


def box_of(pts, rs):
    xs = [p[0] for p in pts] + [c - abs(a) for c, _, a, _ in rs] + [c + abs(a) for c, _, a, _ in rs]
    ys = [p[1] for p in pts] + [c - abs(b) for _, c, _, b in rs] + [c + abs(b) for _, c, _, b in rs]
    return np.array([min(xs) - P2, min(ys) - P2, max(xs) + P2, max(ys) + P2])


def clearance(r, n, na, ra):
    """The narrowest white between the two components of unit n: the least distance
    between their centrelines, less one pen width."""
    ss = [(s, k) for k, (s, o) in enumerate(zip(r["strokes"], r["owner_s"])) if o == n]
    ids = sorted({i for s, _ in ss for i in s})
    first = set(ids[:na])
    def samples(left):
        out = []
        for (i, j), k in ss:
            if (i in first) == left:
                out.append(FR.curve(r["points"][i], r["points"][j], r["bends"][k], n=12))
        rs = [q for q, o in zip(r["rings"], r["owner_r"]) if o == n]
        for q in (rs[:ra] if left else rs[ra:]):
            a = np.linspace(0, 2 * np.pi, 32, endpoint=False)
            out.append(np.column_stack([q[0] + q[2] * np.cos(a), q[1] + q[3] * np.sin(a)]))
        return np.vstack(out) if out else np.zeros((0, 2))
    A, B = samples(True), samples(False)
    if not len(A) or not len(B):
        return np.nan
    d = np.hypot(A[:, None, 0] - B[None, :, 0], A[:, None, 1] - B[None, :, 1]).min()
    return float(d - FR.PEN)


def main(path):
    res = pickle.load(open(path, "rb"))
    single = collections.defaultdict(list)      # (role, jamo, v, hf) -> boxes
    clusters = []                               # (role, cluster, v, hf, left box, right box)
    for cp, r in res.items():
        if not FR.good(r):
            continue
        i, v, f = H.decompose(cp); hf = bool(f)
        for n, (role, name) in enumerate([("I", I[i]), ("V", V[v])] + ([("F", F[f])] if f else [])):
            if role == "V":
                continue
            pts, rs = unit_parts(r, n)
            if name in PAIR:
                a, b = PAIR[name]
                na, ra = len(FR.TEMPLATE[a]["p"]), len(FR.TEMPLATE[a]["r"])
                clusters.append((role, name, v, hf, box_of(pts[:na], rs[:ra]), box_of(pts[na:], rs[ra:]),
                                 clearance(r, n, na, ra)))
            else:
                single[(role, name, v, hf)].append(box_of(pts, rs))
    med = {k: np.median(bs, axis=0) for k, bs in single.items() if len(bs) >= 1}
    rows = collections.defaultdict(list)
    for role, name, v, hf, L, R, cl in clusters:
        a, b = PAIR[name]
        ka, kb = (role, a, v, hf), (role, b, v, hf)
        if ka not in med or kb not in med:
            continue
        A, B = med[ka], med[kb]
        w = lambda q: q[2] - q[0]; h = lambda q: q[3] - q[1]
        rows[(role, name)].append({
            "wL": w(L) / w(A), "wR": w(R) / w(B),            # each component's width against the single
            "hL": h(L) / h(A), "hR": h(R) / h(B),
            "gap": R[0] - L[2],                                # ink gap between the two
            "W": (R[2] - L[0]) / w(A),                         # the cluster's width against the first single
            "left": L[0] - A[0],                               # where the cluster starts against the single
            "bot": (R[1] - L[1]), "top": (R[3] - L[3]), "clear": cl})       # right part against left part, bottom and top
    keys = ["wL", "wR", "hL", "hR", "gap", "W", "left", "bot", "top", "clear"]
    print(f"{'':6}{'n':>4} " + " ".join(f"{k:>6}" for k in keys))
    for (role, name), xs in sorted(rows.items(), key=lambda kv: (kv[0][0] != "I", kv[0][1])):
        print(f"{role} {name} {PAIR[name]} {len(xs):3d} " + " ".join(f"{np.median([x[k] for x in xs]):6.2f}" if k[0] in "wh" or k == "W"
                                                     else f"{np.median([x[k] for x in xs]):6.0f}" for k in keys))


if __name__ == "__main__":
    main(sys.argv[1])

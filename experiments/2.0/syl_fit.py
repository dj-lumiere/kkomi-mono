"""Every drawn syllable fitted as a whole to its initial, vowel and final frames.
The frames start in the median boxes of the parts that split cleanly."""
import sys, pickle, collections, time
from multiprocessing import Pool
ROOT = __import__("os").path.abspath(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "..", ".."))
sys.path.insert(0, ROOT + "/tools"); sys.path.insert(0, ROOT + "/experiments/2.0")
import numpy as np
import make_mono as M, hangul_fill as H, frames as FR, compose as CO
from fontTools.ttLib import TTFont
I = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"; V = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
F = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"
SRC = ROOT + "/source/KNPSKkomi.otf"
cap = pickle.load(open(sys.argv[1], "rb"))
def cs(x): return M.polygon_points_ops(x) if x and not isinstance(x[0], list) else x

# median boxes of clean parts, from fine keys to coarse ones
boxes = collections.defaultdict(list)
for cp in cap["tr"]:
    i, v, f = H.decompose(cp); hf = bool(f); vc = H.vowel_class(v)
    i_cs, v_cs, f_cs = cap["sp"][cp]
    clean = i not in H.DOUBLE_OF and CO.sound(cs(i_cs), cs(v_cs), v)
    if clean and i_cs:
        b = M.bounds(H.flatten(cs(i_cs)))
        for key in (("I", i, v, hf), ("I", i, vc, hf), ("I*", vc, hf)): boxes[key].append(b)
    if clean and v_cs:
        b = M.bounds(H.flatten(cs(v_cs)))
        for key in (("V", v, hf),): boxes[key].append(b)
    if f and f_cs:
        b = M.bounds(H.flatten(cs(f_cs)))
        for key in (("F", f, v), ("F", f, vc), ("F*", vc)): boxes[key].append(b)
# a previous run's good fits: their unit boxes join the medians, their shapes become the frames
LEARN = sys.argv[4] if len(sys.argv) > 4 else None
lboxes = collections.defaultdict(list)    # boxes of units in good fits
if LEARN:
    prev = pickle.load(open(LEARN, "rb"))
    shapes = collections.defaultdict(list)
    for cp, r in prev.items():
        if not FR.good(r):
            continue
        i, v, f = H.decompose(cp); hf = bool(f); vc = H.vowel_class(v)
        names = [I[i], V[v]] + ([F[f]] if f else [])
        for n, b, fr in FR.unit_boxes(r):
            shapes[names[n]].append(fr)
            keys = [(("I", i, v, hf), ("I", i, vc, hf), ("I*", vc, hf)),
                    (("V", v, hf), ("V", v, hf, i in H.DOUBLE_OF), ("V", v, hf, "I", i)),
                    (("F", f, v), ("F", f, vc), ("F*", vc), ("F", f, v, "I", i))][n]
            for key in keys: lboxes[key].append(b)
    for name, fs in shapes.items():
        if len(fs) >= 3:
            FR.FRAMES[name] = FR.mean_frame(fs)
    print("learned frames", sorted((len(fs), n) for n, fs in shapes.items())[:6], "...")
med = {k: tuple(float(np.median([b[n] for b in bs])) for n in range(4)) for k, bs in boxes.items()}
lmed = {k: tuple(float(np.median([b[n] for b in bs])) for n in range(4)) for k, bs in lboxes.items() if len(bs) >= 2}
def box(*keys):
    """Boxes learned from good fits first (any key), then the split medians."""
    for k in keys:
        if k in lmed: return lmed[k]
    for k in keys:
        if k in med: return med[k]

def job(cp):
    tt = TTFont(SRC); gs, cmap = tt.getGlyphSet(), tt.getBestCmap()
    i, v, f = H.decompose(cp); hf = bool(f); vc = H.vowel_class(v)
    single = H.DOUBLE_OF.get(i, i)
    own = cap["sp"].get(cp) or (None, None, None)
    ob = lambda c: M.bounds(H.flatten(cs(c))) if c else None
    parts = [(I[i], "초성", ob(own[0]) or box(("I", i, v, hf), ("I", i, vc, hf), ("I", single, v, hf),
                                            ("I", single, vc, hf), ("I*", vc, hf))),
             (V[v], "중성", ob(own[1]) or box(("V", v, hf), ("V", v, not hf)))]
    if f:
        parts.append((F[f], "종성", ob(own[2]) or box(("F", f, v), ("F", f, vc), ("F*", vc))))
    contours = M.polygon_points_ops(M.record(gs, cmap[cp]))
    try:
        return cp, FR.fit_syllable(contours, parts)
    except Exception as e:
        return cp, {"error": repr(e)}

if __name__ == "__main__":
    tt = TTFont(SRC); cmap = tt.getBestCmap(); gs = tt.getGlyphSet()
    cps = [cp for cp in range(H.BASE, H.BASE + 11172) if cp in cmap and M.bounds(M.record(gs, cmap[cp])) is not None]
    arg = sys.argv[2] if len(sys.argv) > 2 else "1"
    cps = cps[::int(arg)] if arg.isdigit() else [ord(c) for c in arg]
    t0 = time.time()
    with Pool(6) as pool:
        res = dict(pool.imap_unordered(job, cps, chunksize=4))
    print(f"{len(res)} syllables in {time.time() - t0:.0f}s")
    good = FR.good
    ok = sum(good(r) for r in res.values())
    print(f"fit {ok}/{len(res)} = {ok/len(res):.2f}  IoU median {np.median([r['iou'] for r in res.values() if r and 'iou' in r]):.3f}")
    for role_idx, names in ((0, I), (1, V)):
        by = collections.defaultdict(list)
        for cp, r in res.items():
            by[names[H.decompose(cp)[role_idx]]].append(good(r))
        print("by", "초성" if role_idx == 0 else "중성", sorted(((round(sum(x)/len(x), 2), k, len(x)) for k, x in by.items()))[:8])
    print("errors", [r["error"] for r in res.values() if r and "error" in r][:3])
    pickle.dump(res, open(sys.argv[3] if len(sys.argv) > 3 else "syl_fits.pkl", "wb"))

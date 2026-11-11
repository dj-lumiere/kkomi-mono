"""How far 1.8.3 strays from the three rules, measured on its parts (hangul_fill report).
1. syllables differing only in their final: spread of the upper part's top, left, right
2. one vowel over different initials: spread of the upper part's right edge (ㅏ-like vowels)
3. one final under one vowel: spread of the final's top and middle across initials"""
import sys, collections, json
sys.path.insert(0, "/home/lumi/programming/RiderProjects/LumiFoundry/fonts/kkomi-mono/tools")
import numpy as np
from fontTools.ttLib import TTFont
import make_mono_static as MS, hangul_fill as H
tt = TTFont(sys.argv[1]); rep = {}
H.fill(tt.getGlyphSet(), tt.getBestCmap(), MS.embolden, report=rep)
g1 = collections.defaultdict(list); g2 = collections.defaultdict(list); g3 = collections.defaultdict(list)
for cp, (ub, lb, kind) in rep.items():
    i, v, f = H.decompose(cp)
    if f:
        g1[(i, v)].append(ub)
        if lb:
            g3[(f, v)].append(lb)
    if H.vowel_class(v) == 0:
        g2[(v, bool(f))].append(ub)
def spread(groups, fn):
    s = [np.std([fn(b) for b in bs]) for bs in groups.values() if len(bs) >= 3]
    return round(float(np.median(s)), 1), round(float(np.percentile(s, 90)), 1)
out = {
    "1 upper top": spread(g1, lambda b: b[3]), "1 upper left": spread(g1, lambda b: b[0]),
    "1 upper right": spread(g1, lambda b: b[2]),
    "2 vowel right edge": spread(g2, lambda b: b[2]),
    "3 final top": spread(g3, lambda b: b[3]), "3 final middle": spread(g3, lambda b: (b[0] + b[2]) / 2),
}
for k, v in out.items():
    print(f"{k:20} median sd {v[0]:5}  p90 sd {v[1]:5}")
json.dump(out, open(sys.argv[2], "w"), ensure_ascii=False)

"""How much of a jamo's variation does its context explain?
For every initial, its box in each drawn syllable (left, bottom, width, height) is
regressed on the context: which vowel follows, and whether and which final comes.
Prints R^2 (share of variance explained) and the leftover spread, per measure."""
import sys, collections
sys.path.insert(0, "/home/lumi/programming/RiderProjects/LumiFoundry/fonts/kkomi-mono/tools")
import numpy as np
from fontTools.ttLib import TTFont
import make_mono as M, make_mono_static as MS, hangul_fill as H
SRC = sys.argv[1]
tt = TTFont(SRC); gs = tt.getGlyphSet(); cmap = tt.getBestCmap()
cap = {}
orig = H.learn_boxes
def grab(drawn, split_parts, trusted):
    cap["parts"] = {cp: split_parts[cp] for cp in drawn if trusted(cp)}
    return orig(drawn, split_parts, trusted)
H.learn_boxes = grab
H.fill(gs, cmap, MS.embolden, learn=True)
P = cap["parts"]
I = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
GROUP = {1: 1, 2: 1, 3: 2, 4: 1, 5: 2, 6: 2, 7: 1, 8: 1, 9: 2, 10: 2, 11: 2, 12: 2, 13: 2, 14: 2, 15: 2,
         16: 1, 17: 1, 18: 2, 19: 1, 20: 1, 21: 1, 22: 1, 23: 1, 24: 1, 25: 1, 26: 1, 27: 1}
def r2(X, y):
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    res = y - X @ beta
    return 1 - res.var() / y.var(), res.std()
names = ["left", "bottom", "width", "height"]
print(f"{'':4} {'n':>4}  " + "  ".join(f"{n:>16}" for n in names))
allr = collections.defaultdict(list)
for i in range(19):
    rows = [(cp, P[cp][0]) for cp in P if H.decompose(cp)[0] == i]
    if len(rows) < 25:
        continue
    X, Y = [], []
    for cp, ini in rows:
        _, v, f = H.decompose(cp)
        x = np.zeros(1 + 21 + 3)
        x[0] = 1; x[1 + v] = 1; x[22 + (GROUP.get(f, 0))] = 1
        b = M.bounds(H.flatten(ini))
        X.append(x); Y.append([b[0], b[1], b[2] - b[0], b[3] - b[1]])
    X, Y = np.array(X), np.array(Y)
    out = []
    for k in range(4):
        rr, sd = r2(X, Y[:, k]); out.append(f"R2 {rr:4.2f} sd {sd:5.1f}"); allr[names[k]].append(rr)
    print(f"{I[i]:4} {len(rows):>4}  " + "  ".join(f"{o:>16}" for o in out))
print("median R2:", {k: round(float(np.median(v)), 2) for k, v in allr.items()})

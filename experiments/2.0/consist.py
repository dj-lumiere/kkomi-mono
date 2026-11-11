"""2.0 feasibility, part 2: is each jamo drawn with the same stroke structure?
The drawn syllables are split into initial, vowel and final (hangul_fill), each part's
outline is rasterised alone, skeletonised, and its end points and junctions counted.
For every jamo, prints how often its most common structure occurs."""
import sys, collections, json
sys.path.insert(0, "/home/lumi/programming/RiderProjects/LumiFoundry/fonts/kkomi-mono/tools")
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from skimage.morphology import skeletonize
from skan import Skeleton
from fontTools.ttLib import TTFont
import make_mono as M, make_mono_static as MS, hangul_fill as H
SRC, OUT = sys.argv[1], sys.argv[2]
tt = TTFont(SRC); gs = tt.getGlyphSet(); cmap = tt.getBestCmap()
captured = {}
orig = H.learn_boxes
def grab(drawn, split_parts, trusted):
    captured["parts"] = {cp: split_parts[cp] for cp in drawn if trusted(cp)}
    return orig(drawn, split_parts, trusted)
H.learn_boxes = grab
H.fill(gs, cmap, MS.embolden, learn=True)
parts = captured["parts"]
print("trusted syllables", len(parts))
def structure(contours):
    flat = M.flattened(H.flatten(contours))
    b = M.bounds(flat)
    w, h = int(b[2] - b[0]) + 20, int(b[3] - b[1]) + 20
    img = Image.new("L", (w, h), 0); d = ImageDraw.Draw(img)
    for poly in M.polygon_points(flat):
        d.polygon([(x - b[0] + 10, b[3] - y + 10) for x, y in poly], fill=255 if M.signed_area(poly) > 0 else 0)
    m = np.array(img) > 127
    if not m.any():
        return None
    sk = skeletonize(m)
    g = Skeleton(sk)
    deg = g.degrees
    ends = int((deg == 1).sum())
    jun_mask = np.zeros_like(sk, bool)
    coords = g.coordinates.astype(int)
    for idx in np.nonzero(deg >= 3)[0]:
        jun_mask[tuple(coords[idx])] = True
    _, njun = ndimage.label(jun_mask, structure=np.ones((3, 3)))
    holes = int(ndimage.label(~ndimage.binary_fill_holes(m) ^ ~m)[1])
    return (ends, njun)
I = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"; V = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
F = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"
by = {"초성": collections.defaultdict(collections.Counter), "중성": collections.defaultdict(collections.Counter),
      "종성": collections.defaultdict(collections.Counter)}
for cp, (ini, vow, low) in parts.items():
    i, v, f = H.decompose(cp)
    for role, cs, name in (("초성", ini, I[i]), ("중성", vow, V[v]), ("종성", low, F[f] if f else None)):
        if name and cs:
            s = structure(cs)
            if s: by[role][name][s] += 1
report = {}
for role, d in by.items():
    rows = []
    for name, cnt in d.items():
        n = sum(cnt.values()); top, k = cnt.most_common(1)[0]
        rows.append((name, n, top, round(k / n, 2)))
    rows.sort(key=lambda r: r[3])
    report[role] = rows
    shares = [r[3] for r in rows if r[1] >= 10]
    print(role, "jamo", len(rows), "median share of the most common structure", round(float(np.median(shares)), 2),
          "min", min(shares), "(jamo with >= 10 samples)")
    print("  least consistent:", [(r[0], r[1], r[2], r[3]) for r in rows if r[1] >= 10][:6])
json.dump(report, open(f"{OUT}/consist.json", "w"), ensure_ascii=False)

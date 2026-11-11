"""ㅎ syllables built stroke by stroke: tick, bar and ring each placed where the context
model (vowel + final or not, fitted on the designer's 166 ㅎ syllables) puts them. Over
ㅗ ㅘ ㅚ the ring stands on the ㅗ's tick, drawn in one with it, as the designer does."""
import sys, pickle, collections
import numpy as np
sys.path.insert(0, "/home/lumi/programming/RiderProjects/LumiFoundry/fonts/kkomi-mono/tools")
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw
import make_mono as M, make_mono_static as MS, hangul_fill as H, compose as C
import h_strokes as HS

W = MS.embolden
KEYS = ["ring_w", "ring_h", "ring_cx", "ring_bot", "bar_l", "bar_r", "bar_y", "tick_top"]
JOIN = {8, 9, 11}          # ㅗ ㅘ ㅚ: the designer joins the ring to the tick (9/10, 4/8, 5/7)
SRC = sys.argv[1]
tt = TTFont(SRC); gs, cmap = tt.getGlyphSet(), tt.getBestCmap()

# --- the model
data = {}
for cp in range(H.BASE, H.BASE + 11172):
    if H.decompose(cp)[0] != 18 or cp not in cmap: continue
    ops = M.record(gs, cmap[cp])
    if M.bounds(ops) is None: continue
    st = HS.h_strokes(M.polygon_points_ops(ops))
    if st: data[cp] = (st, HS.measure(st))
rows = list(data)
# value = mean + vowel-kind effect + vowel effect + final effect. The vowel effect is held
# back toward its kind (ridge, LAM pseudo-samples), so a vowel with few or no ㅎ samples
# takes the place of its kind.
LAM = 3.0
def feats(v, hf):
    x = np.zeros(1 + 3 + 21 + 1); x[0] = 1; x[1 + H.vowel_class(v)] = 1; x[4 + v] = 1; x[25] = 1 if hf else 0
    return x
X = np.array([feats(H.decompose(cp)[1], bool(H.decompose(cp)[2])) for cp in rows])
pen = np.zeros(26); pen[1:4] = 0.3; pen[4:25] = LAM
A = X.T @ X + np.diag(pen)
COEF = {k: np.linalg.solve(A, X.T @ np.array([data[cp][1][k] for cp in rows])) for k in KEYS}
COUNT = __import__("collections").Counter(H.decompose(cp)[1] for cp in rows)

def predict(v, hf):
    x = feats(v, hf)
    return {k: float(x @ COEF[k]) for k in KEYS}

# --- template strokes: 히, every stroke on its own
tpl_st, tpl_m = data[ord("히")]
tpl_ring = HS.ring_box(tpl_st["ring"])
RING = M.bounds(H.flatten(tpl_st["ring"][1:]))[1] - tpl_ring[1]     # the ring's stroke, from below
BAR = 68                                                                # a flat stroke's height

def scaled(cs, src, dst):
    """contours in box src moved and scaled to box dst, strokes kept as thick."""
    kx = (dst[2] - dst[0]) / (src[2] - src[0]); ky = (dst[3] - dst[1]) / (src[3] - src[1])
    out = M.transformed(H.flatten(cs), kx, dst[0] - kx * src[0], ky, dst[1] - ky * src[1])
    return M.polygon_points_ops(W(out, 68 * (1 - kx), 68 * (1 - ky)))

def build_h(p, vowel, v):
    """the ㅎ for predicted strokes p, kept clear of the vowel. Returns contours."""
    ub = C.box(vowel)
    tall, flat = C.split_vowel(vowel, ub[3] - 0)
    tall = [q for q in vowel if M.bounds(q)[3] - M.bounds(q)[1] > 400]
    flat = [q for q in vowel if not any(q is t for t in tall)]
    right = min((M.bounds(q)[0] for q in tall), default=1e9) - C.GAP_SIDE
    bar_r = min(p["bar_r"], right)
    # the ring keeps inside the bar's span: narrower only when it must, moved left first
    ring_w = min(p["ring_w"], bar_r - p["bar_l"] - 20)
    p = dict(p, ring_cx=min(p["ring_cx"], bar_r - 10 - ring_w / 2))
    ring_bot = p["ring_bot"]
    ring_top = ring_bot + p["ring_h"]
    tick_x = None
    if flat and H.vowel_class(v) != 0:
        fb = C.box(flat)
        if v in JOIN:
            # the ㅗ's tick: the highest point of the flat part. Its own tick is cut off
            # at the bar and the ring's stem takes its place.
            pts = [pt for q in flat for poly in M.polygon_points(M.flattened(q)) for pt in poly]
            tick_x = max(pts, key=lambda pt: pt[1])[0]
            bar_bot = min(M.bounds(q)[1] for q in flat if M.bounds(q)[2] - M.bounds(q)[0] > 200)
            bar_top = bar_bot + BAR
            cut = M.clip_polygon(H.flatten(flat), [(-300, -400), (-300, bar_top), (1300, bar_top), (1300, -400)])
            vowel = tall + H.same_way(M.polygon_points_ops(cut), flat)
            ring_bot = max(ring_bot, bar_top + 45)
        else:
            ring_bot = max(ring_bot, fb[3] + C.GAP_ABOVE)
    # the ring shrinks from below when pushed up, the bar and tick stay
    ring_top = max(ring_top, ring_bot + 150)
    ring_top = min(ring_top, p["bar_y"] - 35)
    cx = tick_x if tick_x is not None else p["ring_cx"]
    ring = scaled(tpl_st["ring"], tpl_ring, (cx - ring_w / 2, ring_bot, cx + ring_w / 2, ring_top))
    bb = M.bounds(H.flatten(tpl_st["bar"]))
    bar = scaled(tpl_st["bar"], bb, (p["bar_l"], p["bar_y"], bar_r, p["bar_y"] + bb[3] - bb[1]))
    tb = M.bounds(H.flatten(tpl_st["tick"]))
    dx = (p["bar_l"] + bar_r) / 2 - (tpl_m["bar_l"] + tpl_m["bar_r"]) / 2
    tick = H.shift(tpl_st["tick"], dx, p["tick_top"] - tb[3])
    out = ring + bar + tick
    if tick_x is not None:
        # the stem from the ring down into the ㅗ
        import symbols
        stem = symbols.pen_stroke((tick_x, ring_bot + RING / 2 - 5), [("line", (tick_x, bar_bot + BAR / 2))], 60)
        out += H.same_way(M.polygon_points_ops(stem), tpl_st["bar"])
    return out, vowel

# --- compose
out, stats, info, hp = C.compose(gs, cmap, W)
def cs_of(x):
    return M.polygon_points_ops(x) if x and not isinstance(x[0], list) else x

def syllable(cp):
    i, v, f = H.decompose(cp); hf = bool(f)
    vowel = cs_of(hp["vowel"](v, hf))
    h, vowel = build_h(predict(v, hf), vowel, v)
    up = h + vowel
    if not f:
        return H.flatten(up)
    fp = H.flatten(cs_of(hp["final"](f, v)))
    d = max(hp["drop"].get((f, v), 0.0), C.CLEAR - H.gap_below(up, fp))
    if d > 0: fp = M.transformed(fp, 1.0, 0.0, 1.0, -d)
    return H.flatten(up) + fp

# --- error of the ㅎ against the designer's, over all drawn ㅎ syllables
def h_err(ops, cp):
    st = HS.h_strokes(M.polygon_points_ops(ops))
    if not st: return None
    m = HS.measure(st)
    return np.mean([abs(m[k] - data[cp][1][k]) for k in KEYS])
e_old, e_new = [], []
for cp in rows:
    a = h_err(out[cmap[cp]], cp); b = h_err(syllable(cp), cp)
    if a is not None and b is not None: e_old.append(a); e_new.append(b)
print(f"ㅎ stroke error vs designer (mean over 8 measures, units): part composition median {np.median(e_old):.1f}, stroke composition median {np.median(e_new):.1f}  (n={len(e_old)})")

# --- sheet
drawn_txt = "하호회화효혜히흐희흑흙휘훼홰"
built = [ch for ch in "홟훯횕흝혩햳홦휽흖횙" if ch not in "".join(chr(c) for c in data)][:8]
import os; k = float(os.environ.get("K", "0.09")); cell = 1000 * k; rowh = 1250 * k
labels = ["원본 / 1.8.3", "부품 조합", "획 조합"]
cols = list(os.environ.get("CHARS", drawn_txt + " " + "".join(built)))
fill183 = H.fill(gs, cmap, W)[0]
img = Image.new("L", (int(cell * len(cols)) + 20, int(rowh * 3) + 20), 0)
dr = ImageDraw.Draw(img)
def put(ops, x, y):
    for poly in M.polygon_points(ops):
        if len(poly) > 2:
            dr.polygon([(x + px * k, y + (1000 - py) * k) for px, py in poly], fill=0 if M.signed_area(poly) * (1 if M.CLOCKWISE else 1) > 0 else 255)
import pathops
from fontTools.pens.recordingPen import RecordingPen
from PIL import ImageChops
def put_lines(ops, x, y):
    path = pathops.Path(); pp = path.getPen()
    for op, args in ops:
        getattr(pp, op)(*args)
    path.simplify(fix_winding=True)
    rec = RecordingPen(); path.draw(rec)
    global img, dr
    for poly in M.polygon_points(M.flattened(rec.value)):
        if len(poly) < 3: continue
        m = Image.new("L", img.size, 0)
        ImageDraw.Draw(m).polygon([(x + px * k, y + (1000 - py) * k) for px, py in poly], fill=255)
        img = ImageChops.difference(img, m)
    dr = ImageDraw.Draw(img)
for r in range(3):
    for n, ch in enumerate(cols):
        if ch == " ": continue
        cp = ord(ch); x = 10 + n * cell; y = 10 + r * rowh
        if r == 0:
            ops = M.record(gs, cmap[cp]) if cp in data else fill183[cmap[cp]]
        elif r == 1:
            ops = out[cmap[cp]]
        else:
            ops = syllable(cp)
        put_lines(ops, x, y)
ImageChops.invert(img).save(sys.argv[2])
print("built", "".join(built)); print("ㅎ samples per vowel", dict(sorted(COUNT.items())))

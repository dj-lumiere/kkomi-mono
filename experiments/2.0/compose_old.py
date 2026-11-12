"""Old Hangul syllables drawn from the learned jamo frames and the cluster rules.

Layout, three levels:
  syllable -> regions: the initial, vowel and final boxes learned from the fits of modern
              syllables (a cluster of two or more takes the region of a modern double,
              ㄲ ㄸ ㅃ ㅆ ㅉ for an initial, ㄺ for a final, and the vowel moves as it does
              next to a double).
  region   -> components: side by side, widths in proportion to the single jamo's widths
              in that place, heights as the single jamo has them; between two components
              a box gap of 35, or -35 when both are slanted (ㅅ ㅈ ㅊ interlock).
              Three components share the region by the same rule.
  component-> strokes: the jamo's learned frame (mean of its fits) in its box, drawn with
              one round pen.
Light consonants (연서: ᄫ ᄝ ᅗ ...) stack the consonant over a small ㅇ, in two
versions: A shares the height evenly (the cluster rule turned upright), B gives ㅇ a third.
Sibilant variants: 치두 (ᄼ ᅎ ᅔ) shortens the right leg, 정치 (ᄾ ᅐ ᅕ) cuts the left
stroke just below where the right leg leaves it and runs the right leg to the baseline.
usage: compose_old.py split_all.pkl prep.pkl fits.pkl out.png"""
import os, sys, unicodedata
import numpy as np
from PIL import Image, ImageDraw

SPLIT, PREP, FITS, SHEET = sys.argv[1:5]
sys.argv = ["fast_run.py", SPLIT, PREP, "1", "unused.pkl", FITS]
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fast_run.py")).read().split("if __name__")[0])

NAME = {"KIYEOK": "ㄱ", "NIEUN": "ㄴ", "TIKEUT": "ㄷ", "RIEUL": "ㄹ", "MIEUM": "ㅁ", "PIEUP": "ㅂ", "SIOS": "ㅅ",
        "IEUNG": "ㅇ", "CIEUC": "ㅈ", "CHIEUCH": "ㅊ", "KHIEUKH": "ㅋ", "THIEUTH": "ㅌ", "PHIEUPH": "ㅍ", "HIEUH": "ㅎ",
        "YEORINHIEUH": "ㆆ"}
SLANT = set("ㅅㅈㅊ")
BOXOF = {"ㆆ": "ㅇ"}      # a jamo without its own fits takes the boxes of this one
DOUBLE_OF_FIRST = {"ㄱ": 1, "ㄷ": 4, "ㅂ": 8, "ㅅ": 10, "ㅈ": 13}
PEN = FR.PEN
ROLES = []
CELL = (13, -153, 844, 819)      # where 98% of the designer's syllables put their ink
TOP = 900
GRID_COL = {"I": (230, 120, 120), "V": (110, 150, 230), "F": (100, 180, 110)}


def parse(ch):
    """A conjoining consonant as (components, light): components [(jamo, variant)]."""
    n = unicodedata.name(ch).split(" ", 2)[2]
    comps, light = [], False
    for tok in n.split("-"):
        var = None
        for pre, v in (("CHITUEUM", "chi"), ("CEONGCHIEUM", "jeong")):
            if tok.startswith(pre):
                tok, var = tok[len(pre):], v
        if tok.startswith("KAPYEOUN"):
            tok, light = tok[len("KAPYEOUN"):], True
        k = 2 if tok.startswith("SSANG") else 1
        tok = tok[5:] if k == 2 else tok
        comps += [(NAME[tok], var)] * k
    return comps, light


def variant(frame, jamo, var):
    """치두 / 정치 forms of ㅅ ㅈ ㅊ, from the jamo's own frame."""
    if var is None:
        return frame
    p = [np.array(q, float) for q in frame["p"]]
    o = {"ㅅ": 0, "ㅈ": 1, "ㅊ": 3}[jamo]          # the slanted stroke: o -> o+1, leg: o+2 -> o+3
    if jamo == "ㅅ":
        top, foot, br, end = 0, 1, 2, 3
    else:
        top, foot, br, end = o, o + 1, o + 2, o + 3
    if var == "chi":
        p[end] = p[br] + 0.5 * (p[end] - p[br])
    else:
        low = p[foot][1]
        p[foot] = p[br] + 0.3 * (p[foot] - p[br])
        d = p[end] - p[br]
        if d[1] < -1e-6:
            p[end] = p[br] + d * ((p[br][1] - low) / -d[1])
    out = dict(frame); out["p"] = [tuple(q) for q in p]
    return out


def yeorin():
    """ㆆ: the learned ㅎ without its tick (stroke 0), the bar and ring spread to the full height."""
    f = FR.FRAMES["ㅎ"]
    s0 = f["s"][0]
    keep = [i for i in range(len(f["p"])) if i not in s0]
    pts = np.array([f["p"][i] for i in keep]); rs = np.array(f["r"], float).reshape(-1, 4)
    lo = min(pts[:, 1].min(), (rs[:, 1] - rs[:, 3]).min()); hi = max(pts[:, 1].max(), (rs[:, 1] + rs[:, 3]).max())
    sy = lambda y: (y - lo) / (hi - lo)
    out = FR.F([(x, sy(y)) for x, y in pts], [(keep.index(i), keep.index(j)) for i, j in f["s"][1:]],
               [(cx, sy(cy), rx, ry / (hi - lo)) for cx, cy, rx, ry in rs])
    if "b" in f:
        out["b"] = list(f["b"][1:])
    return out


def gap_to_vowel(comps, light):
    """White between the initial and the vowel's vertical part: 30 as in modern syllables,
    15 beside a cluster (written close, so the cluster keeps its size)."""
    return 15 if len(comps) > 1 and not light else 30


def jamo_parts(j, var, b):
    """A component's parts in box b. ㆆ takes ㅇ's box: the ring pressed down to make room,
    a bar over it, 30 units apart."""
    if j == "ㅣ":
        return [(FR.FRAMES["ㅣ"], flat("ㅣ", b))]
    if j in V:
        return [(FR.FRAMES[j], b)]
    if j != "ㆆ":
        return [(frame_of(j, var), b)]
    x0, y0, x1, y1 = b
    w = x1 - x0
    bar = (x0, y1 - PEN, x1, y1)
    ring = (x0, y0, x1, y1 - PEN - 30)
    return [(FR.chain((0, 0.5), (1, 0.5)), bar), (FR.FRAMES["ㅇ"], ring)]


def frame_of(jamo, var=None):
    if jamo == "ㆆ":
        return yeorin()
    return variant(FR.FRAMES[jamo], jamo, var)


def _min_widths():
    """The narrowest each jamo is drawn (5th percentile of its box widths over the good
    fits, inside clusters as well): a component is never made narrower, so a ㅂ keeps
    its inner white."""
    import pickle, collections
    import cluster_measure as CM
    res = pickle.load(open(FITS, "rb"))
    ws = collections.defaultdict(list)
    for cp, r in res.items():
        if not FR.good(r):
            continue
        i, v, f = H.decompose(cp)
        for n, (role, name) in enumerate([("I", I[i]), ("V", V[v])] + ([("F", F[f])] if f else [])):
            pts, rs = CM.unit_parts(r, n)
            if role != "V" and name in CM.PAIR:
                a, b = CM.PAIR[name]
                na, ra = len(FR.TEMPLATE[a]["p"]), len(FR.TEMPLATE[a]["r"])
                for j, p, q in ((a, pts[:na], rs[:ra]), (b, pts[na:], rs[ra:])):
                    bx = CM.box_of(p, q); ws[(role, j)].append(bx[2] - bx[0])
            else:
                bx = CM.box_of(pts, rs); ws[(role, name)].append(bx[2] - bx[0])
    return {k: float(np.percentile(x, 5)) for k, x in ws.items()}


MINW = _min_widths()


def place_row(region, comps, singles, mins, lo, hi, hard=False):
    """Boxes for components side by side, starting at the region's left. Widths are the
    region shared in proportion to the singles' widths, but never under `mins`; when that
    makes the row longer it moves left (not past lo). Returns the boxes and the row's
    right end, which may pass hi: the caller makes room (moves the vowel)."""
    x0, y0, x1, y1 = region
    white = 10 if len(comps) >= 3 else 35       # three consonants keep their size, not their white
    gaps = [(-35 if a[0] in SLANT and b[0] in SLANT else white) for a, b in zip(comps, comps[1:])]
    ws = np.array([s[2] - s[0] for s in singles], float)
    room = (x1 - x0) - sum(gaps)
    widths = np.maximum(room * ws / ws.sum(), np.array(mins, float))
    total = widths.sum() + sum(gaps)
    if x0 + total > hi:
        x0 = max(lo, hi - total)
    if hard and x0 + total > hi:
        # no room to give: every component narrowed by one factor, the least widths too
        f = (hi - x0 - sum(gaps)) / widths.sum()
        widths = widths * f
        total = widths.sum() + sum(gaps)
    out, x = [], x0
    for k, s in enumerate(singles):
        out.append((x, s[1], x + widths[k], s[3]))
        x += widths[k] + (gaps[k] if k < len(gaps) else 0)
    return out, x0 + total


def widen(region, singles, n, lo, hi, centred):
    """A cluster of n takes the region of a two-cluster widened again by what two gained
    over one (W_n = W_2 + (n - 2)(W_2 - W_1)), kept within lo..hi."""
    x0, y0, x1, y1 = region
    W1 = float(np.mean([s[2] - s[0] for s in singles]))
    W2 = x1 - x0
    extra = (n - 2) * max(W2 - W1, 0)
    if centred:
        x0, x1 = x0 - extra / 2, x1 + extra / 2
    else:
        x1 = x1 + extra
    if x1 > hi:
        x0 -= x1 - hi; x1 = hi
    if x0 < lo:
        x1 = min(hi, x1 + lo - x0); x0 = lo
    return (x0, y0, x1, y1)


def light_boxes(region, version):
    """The consonant over a small ㅇ: version A halves the height, B gives ㅇ a third,
    C (the one chosen) splits it 60:40."""
    x0, y0, x1, y1 = region
    Hh = y1 - y0
    share = {"A": 0.5, "B": 1 / 3}.get(version, 0.4)     # the ring's share of the height
    ring = max((Hh - 35) * share, PEN * 1.6)
    cx = (x0 + x1) / 2
    return (x0, y0 + ring + 35, x1, y1), (cx - ring / 2, y0, cx + ring / 2, y0 + ring)


def initial_parts(ch, v, hf, version, vb, vx0=None, hard=False):
    """The initial's parts and its right end (the vowel moves if this passes its start)."""
    vc = H.vowel_class(v)
    comps, light = parse(ch)
    sbox0 = lambda j: box(("I", I.index(BOXOF.get(j, j)), v, hf), ("I", I.index(BOXOF.get(j, j)), vc, hf), ("I*", vc, hf))
    if EXTRA[0] and not light:
        comps = comps + [(e, None) for e in EXTRA[0]]
    def sbox(j):
        if j in V:                       # a vowel standing in the row, as tall as the first consonant
            f = sbox0(comps[0][0])
            w = PEN + 50 if j == "ㅣ" else 0.8 * (lambda q: q[2] - q[0])(box(("V", V.index(j), hf), ("V", V.index(j), not hf)))
            return (0, f[1], w, f[3])
        return sbox0(j)
    if light:
        j, var = comps[0]
        top, low = light_boxes(sbox(j), version)
        return [(frame_of(j, var), top), (FR.FRAMES["ㅇ"], low)], top[2]
    if len(comps) == 1:
        j, var = comps[0]
        b = sbox(j)
        return jamo_parts(j, var, b), b[2]
    d = DOUBLE_OF_FIRST.get(comps[0][0], 1)
    region = box(("I", d, v, hf), ("I", d, vc, hf), ("I", 1, v, hf), ("I", 1, vc, hf))
    singles = [sbox(j) for j, _ in comps]
    # a vowel's vertical part stops the initial. Beside a vowel on the right the vowel
    # can move; above a mixed vowel (ㅙ) it cannot, and the initial is narrowed instead
    right = (vx0 - gap_to_vowel(comps, light)) if vx0 is not None else CELL[2]
    region = widen(region, singles, len(comps), CELL[0] + 20, right, centred=False)
    boxes, end = place_row(region, comps, singles, [MINW.get(("I", BOXOF.get(j, j)), PEN + 30) if j not in V else (PEN + 30) for j, _ in comps],
                           CELL[0] + 20, right, hard=hard)
    return [q for (j, var), b in zip(comps, boxes) for q in jamo_parts(j, var, b)], end


def final_parts(ch, v):
    vc = H.vowel_class(v)
    comps, light = parse(ch)
    sbox = lambda j: box(("F", F.index(BOXOF.get(j, j)), v), ("F", F.index(BOXOF.get(j, j)), vc), ("F*", vc))
    if len(comps) == 1:
        return jamo_parts(comps[0][0], comps[0][1], sbox(comps[0][0]))
    region = box(("F", 9, v), ("F", 9, vc), ("F*", vc))
    singles = [sbox(j) for j, _ in comps]
    region = widen(region, singles, len(comps), CELL[0] + 20, CELL[2] - 20, centred=True)
    boxes, _ = place_row(region, comps, singles, [MINW.get(("F", BOXOF.get(j, j)), 0) for j, _ in comps],
                         CELL[0] + 20, CELL[2] - 20)
    return [q for (j, var), b in zip(comps, boxes) for q in jamo_parts(j, var, b)]


# vowels -------------------------------------------------------------------------
VTOK = {"A": "ㅏ", "AE": "ㅐ", "YA": "ㅑ", "YAE": "ㅒ", "EO": "ㅓ", "E": "ㅔ", "YEO": "ㅕ", "YE": "ㅖ",
        "O": "ㅗ", "YO": "ㅛ", "U": "ㅜ", "YU": "ㅠ", "EU": "ㅡ", "YI": "ㅢ", "I": "ㅣ", "ARAEA": "ㆍ",
        "WA": "ㅘ", "WAE": "ㅙ", "OE": "ㅚ", "WEO": "ㅝ", "WE": "ㅞ", "WI": "ㅟ"}
HOR = set("ㅗㅛㅜㅠㅡㆍ")
TWO = set("ㅐㅒㅔㅖ")
# a modern compound vowel lending its layout: (horizontal family, two stems, bare ㅣ)
MODEL = {("ㅗ", False, False): "ㅘ", ("ㅗ", True, False): "ㅙ", ("ㅗ", False, True): "ㅚ",
         ("ㅜ", False, False): "ㅝ", ("ㅜ", True, False): "ㅞ", ("ㅜ", False, True): "ㅟ",
         ("ㅡ", False, True): "ㅢ"}
# its strokes: the horizontal part, the vertical part
GROUPS = {"ㅘ": ([0, 1], [2, 3]), "ㅙ": ([0, 1], [2, 3, 4]), "ㅚ": ([0, 1], [2]),
          "ㅝ": ([0, 1], [2, 3]), "ㅞ": ([0, 1], [2, 3, 4]), "ㅟ": ([0, 1], [2]), "ㅢ": ([0], [1])}


def vowel_tokens(ch):
    if ch in V:
        return [ch]
    out = []
    for t in unicodedata.name(ch).split(" ", 2)[2].split("-"):
        if t.startswith("SSANG"):
            out += [VTOK[t[5:]]] * 2
        elif t == "YI":
            out += ["ㅡ", "ㅣ"]          # ㅢ inside an old vowel is its two parts
        else:
            out.append(VTOK[t])
    return out


def flat(j, b):
    """ㅡ and ㅣ are one stroke whose frame has almost no height (width): set in a box of
    their own pen width, in the middle of b, so the box's other side does not tilt them."""
    x0, y0, x1, y1 = b
    if j == "ㅡ":
        c = (y0 + y1) / 2
        return (x0, c - PEN / 2 - 4, x1, c + PEN / 2 + 4)
    if j == "ㅣ":
        c = (x0 + x1) / 2
        return (c - PEN / 2 - 4, y0, c + PEN / 2 + 4, y1)
    return b


def jamo_part(j, b):
    return ("dot", b) if j == "ㆍ" else (FR.FRAMES[j], flat(j, b))


def sub_frame(frame, strokes):
    """The strokes `strokes` of a frame as a frame of their own, spread over its box."""
    ids = sorted({i for k in strokes for i in frame["s"][k]})
    pts = np.array([frame["p"][i] for i in ids], float)
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    span = np.where(hi - lo > 1e-6, hi - lo, 1.0)
    q = [tuple(np.where(hi - lo > 1e-6, (p - lo) / span, 0.5)) for p in pts]
    out = FR.F(q, [(ids.index(frame["s"][k][0]), ids.index(frame["s"][k][1])) for k in strokes])
    if "b" in frame:
        out["b"] = [frame["b"][k] for k in strokes]
    return out


def group_box(frame, vb, strokes):
    g = FR.in_box(frame, vb)
    pts = np.array([g["p"][i] for k in strokes for i in g["s"][k]])
    return (pts[:, 0].min() - PEN / 2, pts[:, 1].min() - PEN / 2, pts[:, 0].max() + PEN / 2, pts[:, 1].max() + PEN / 2)


def stack(hs, b, dot_y=None):
    """One or two horizontal vowels in box b; two are stacked, or for ᆢ without room set
    side by side like ‥ at dot_y (where ㅡ is)."""
    if len(hs) == 1:
        return [jamo_part(hs[0], b)]
    if hs in (["ㅗ", "ㅗ"], ["ㅜ", "ㅜ"]):
        # two ㅗ as one shape like 土: one stem through a bar down to a second bar of the
        # same length (ㅜㅜ the same upside down)
        up = hs[0] == "ㅗ"
        y_end, y_mid = (0, 0.5) if up else (1, 0.5)
        f = FR.F([(0.5, 1), (0.5, 0), (0, y_mid), (1, y_mid), (0, y_end), (1, y_end)],
                 [(0, 1), (2, 3), (4, 5)])
        TALL[0] = True
        return [(f, b)]
    mid = (b[1] + b[3]) / 2
    dot = 2 * 0.8 * PEN
    if hs == ["ㆍ", "ㆍ"] and mid - 18 - b[1] < dot:
        cx, cy = (b[0] + b[2]) / 2, (dot_y if dot_y is not None else mid)
        return [("dot", (cx - dot - 10, cy - 1, cx - 10, cy + 1)), ("dot", (cx + 10, cy - 1, cx + dot + 10, cy + 1))]
    return [jamo_part(hs[0], (b[0], mid + 18, b[2], b[3])), jamo_part(hs[1], (b[0], b[1], b[2], mid - 18))]


STYLE = ["C"]        # the current item's style, set by syllable()
EXTRA = [[]]         # vowels written in the initial's row (the first ㅣ of ㅣㅗㅣ)
TALL = [False]       # the vowel under the initial has two bars (土, ‡) and needs height


def vowel_layout(ch, hf, double):
    """(modern vowel index that sets the layout, the vowel's parts, its box, where its
    vertical part starts or None).
    Horizontal vowels before the first vertical one go under the initial; vertical vowels
    stand as columns on the right, left to right; a horizontal vowel after a vertical one
    hangs under that column."""
    toks = vowel_tokens(ch)
    vbox = lambda m: box(("V", V.index(m), hf, double), ("V", V.index(m), hf), ("V", V.index(m), not hf))
    ybar = lambda: (lambda q: (q[1] + q[3]) / 2)(vbox("ㅡ"))
    if len(toks) == 1 and toks[0] in V:
        m = toks[0]; b = vbox(m)
        if m in GROUPS:          # a mixed vowel as its two parts, so the vertical one can move
            gh, gv = GROUPS[m]
            mf = FR.FRAMES[m]
            hb, vb2 = group_box(mf, b, gh), group_box(mf, b, gv)
            return V.index(m), [(sub_frame(mf, gh), hb), (sub_frame(mf, gv), vb2)], b, vb2[0], 1, False
        return V.index(m), [(FR.FRAMES[m], b)], b, (b[0] if H.vowel_class(V.index(m)) == 0 else None), 0, False
    if toks == ["ㅜ", "ㅓ", "ㅡ"]:
        # ᆋ: ㅝ with one more bar under it
        b = vbox("ㅝ")
        mf = FR.FRAMES["ㅝ"]; gh, gv = GROUPS["ㅝ"]
        up = (b[0], b[1] + PEN + 40, b[2], b[3])
        hb, vb2 = group_box(mf, up, gh), group_box(mf, up, gv)
        bar = (b[0], b[1], vb2[2], b[1] + PEN)
        return V.index("ㅝ"), [(sub_frame(mf, gh), hb), (FR.FRAMES["ㅡ"], flat("ㅡ", bar)), (sub_frame(mf, gv), vb2)], b, vb2[0], 2, False
    if toks == ["ㅗ", "ㅗ", "ㅣ"]:
        # ‡ in ㅗ's place, under the initial: one stem crossed by two bars
        b = vbox("ㅜ")
        f = FR.F([(0.5, 1), (0.5, 0), (0, 0.8), (1, 0.8), (0, 0.2), (1, 0.2)], [(0, 1), (2, 3), (4, 5)])
        TALL[0] = True
        return V.index("ㅜ"), [(f, b)], b, None, 1, False
    if toks[0] not in HOR and any(t in HOR for t in toks) and toks != ["ㅣ", "ㆍ"]:
        # vertical vowels before the first horizontal one stand in the initial's row as
        # if consonants (ㅣㅑ of ㅣㅑㅗ); from the first horizontal vowel on, the rest
        # takes the vowel's place under the initial (ㅗ; ㅗ+ㅣ as a cross 十)
        k = next(i for i, t in enumerate(toks) if t in HOR)
        lead, rest = toks[:k], toks[k:]
        if all(t not in HOR for t in lead):
            EXTRA[0] = lead
            if len(rest) == 2 and rest[1] == "ㅣ" and rest[0] in "ㅗㅜ":
                b = vbox("ㅜ")
                f = FR.F([(0.5, 1), (0.5, 0), (0, 0.62), (1, 0.62)], [(0, 1), (2, 3)])
                return V.index("ㅜ"), [(f, b)], b, None, 1, False
            if all(t in HOR for t in rest) and len(rest) <= 2:
                m = rest[0] if rest[0] in V and len(rest) == 1 else ("ㅡ" if rest == ["ㆍ"] else "ㅜ")
                b = vbox(m)
                ps = stack(rest, b, ybar()) if len(rest) == 2 else [jamo_part(rest[0], b)]
                return V.index(m), ps, b, None, len(ps), False
            EXTRA[0] = []
    pre, k = [], 0
    while k < len(toks) and toks[k] in HOR:
        pre.append(toks[k]); k += 1
    cols = []
    for t in toks[k:]:
        if t in HOR:
            cols[-1][1].append(t)
        else:
            cols.append([t, []])
    if not cols:
        if pre == ["ㆍ"]:
            b = vbox("ㅡ")
            return V.index("ㅡ"), [("dot", b)], b, None, 1, False
        b = vbox("ㅜ")
        hs = stack(pre, b, ybar())
        return V.index("ㅜ"), hs, b, None, len(hs), False
    stems = sum(2 if c[0] in TWO else 1 for c in cols)
    lay_long = False
    if pre:
        fam = "ㅗ" if pre[0] in "ㅗㅛ" else "ㅜ" if pre[0] in "ㅜㅠ" else "ㅡ"
        bare = len(cols) == 1 and cols[0][0] == "ㅣ" and not cols[0][1]
        model = MODEL.get((fam, stems >= 2, bare)) or {"ㅗ": "ㅙ" if stems >= 2 else "ㅘ",
                                                      "ㅜ": "ㅞ" if stems >= 2 else "ㅝ"}.get(fam, "ㅢ" if bare else "ㅝ")
        b = vbox(model); gh, gv = GROUPS[model]; mf = FR.FRAMES[model]
        hparts = stack(pre, group_box(mf, b, gh), ybar())
        region = group_box(mf, b, gv)
    elif any(h for _, h in cols):
        # a vertical vowel then a horizontal one (ᅶ ㅏ+ㅗ): laid out as the modern mixed
        # vowel of that pair (ㅘ), with the horizontal vowel drawn long, under the vertical
        # one too, and the vertical one ending above it
        hs = [h for _, hang in cols for h in hang]
        fam = "ㅗ" if hs[0] in "ㅗㅛ" else "ㅜ" if hs[0] in "ㅜㅠ" else "ㅡ"
        bare = len(cols) == 1 and cols[0][0] == "ㅣ"
        model = MODEL.get((fam, stems >= 2, bare)) or {"ㅗ": "ㅙ" if stems >= 2 else "ㅘ",
                                                      "ㅜ": "ㅞ" if stems >= 2 else "ㅝ"}.get(fam, "ㅢ" if bare else "ㅝ")
        b = vbox(model); gh, gv = GROUPS[model]; mf = FR.FRAMES[model]
        hb = group_box(mf, b, gh); region = group_box(mf, b, gv)
        cols = [[vt, []] for vt, _ in cols]
        if len(cols) > 1 or stems >= 2:
            # two columns (ퟁ ㅣ+ㅗ+ㅣ): they keep their full height, the horizontal vowel
            # runs under the initial and across the first column (as Nanum Yet Hangul does)
            hparts = stack(hs[:2], (hb[0], hb[1], max(hb[2], region[0] + 0.5 * (region[2] - region[0]) / len(cols)), hb[3]), ybar())
        elif hs == ["ㆍ"]:
            # ㆍ after a vertical vowel (ᆝ): a dot under the stem, the stem ending above it
            dot = 2 * 0.8 * PEN
            region = (region[0], region[1] + dot + 30, region[2], region[3])
            hparts = [("dot_under", (region[0], region[1] - dot - 30, region[2], region[1] - 30))]
        else:
            top_h = hb[3] if fam != "ㅜ" else (hb[1] + hb[3]) / 2
            region = (region[0], max(region[1], top_h + 30), region[2], region[3])
            hparts = stack(hs[:2], (hb[0], hb[1], region[2], hb[3]), ybar())
            lay_long = True
    else:
        model = "ㅐ" if stems >= 2 or len(cols) > 1 else cols[0][0]
        b = vbox(model); hparts = []
        region = b
    # columns share the region in proportion to their own widths, at least their natural sum
    nat = [vbox(c[0])[2] - vbox(c[0])[0] for c in cols]
    need = sum(nat) + 40 * (len(cols) - 1)
    x0, y0, x1, y1 = region
    if x1 - x0 < need:
        x0 = x1 - need
    room = (x1 - x0) - 40 * (len(cols) - 1)
    parts, x = list(hparts), x0
    for (vt, hang), w in zip(cols, nat):
        cw = room * w / sum(nat)
        cb = (x, y0, x + cw, y1)
        if hang:
            hh = (y1 - y0) * (0.36 if hang[0] in "ㅗㅛㅜㅠ" else 0.2)
            hw = max(cw, 240)
            parts.append((FR.FRAMES[vt], flat(vt, (cb[0], y0 + hh + 30, cb[2], y1))))
            parts += stack(hang, (cb[2] - hw, y0, cb[2], y0 + hh))
        else:
            parts.append((FR.FRAMES[vt], flat(vt, cb)))
        x += cw + 40
    for k, q in enumerate(parts):
        if q[0] == "dot_under":
            col = parts[-1][1]
            cx = (col[0] + col[2]) / 2
            if vowel_tokens(ch)[0] != "ㅣ":
                g = FR.in_box(parts[-1][0], col)
                cx = max(g["p"], key=lambda t: -t[1])[0]       # the stem's lowest point
            dot = 2 * 0.8 * PEN
            y1 = q[1][3]
            parts[k] = ("dot", (cx - dot / 2, y1 - dot, cx + dot / 2, y1))
    lay = V.index(model)
    whole = (min(p[1][0] for p in parts), y0 if not pre else b[1], max(p[1][2] for p in parts), y1)
    return lay, parts, whole, x0, len(hparts), lay_long


def shift_x(part, x0, x1, nx0, nx1):
    """A part moved from x0..x1 to nx0..nx1."""
    f = lambda x: nx0 + (x - x0) * (nx1 - nx0) / max(x1 - x0, 1)
    b = part[1]
    return (part[0], (f(b[0]), b[1], f(b[2]), b[3]))


def syllable(text, version="C"):
    """text: initial, vowel, final (conjoining jamo, or compatibility jamo for modern)."""
    L, Vc = text[0], text[1]
    T = text[2] if len(text) > 2 else None
    hf = T is not None
    Lc = L if "CHOSEONG" in unicodedata.name(L) else chr(0x1100 + I.index(L))
    comps, light = parse(Lc)
    double = len(comps) > 1 and not light
    STYLE[0] = version
    EXTRA[0] = []
    TALL[0] = False
    v, vparts, vb, vx0, nh, long_h = vowel_layout(Vc, hf, double)
    vx0_first = vx0
    G = gap_to_vowel(comps, light)
    vc = H.vowel_class(v)
    parts, end = initial_parts(Lc, v, hf, version, vb, vx0)
    if vc == 2 and vx0 is not None and end + G > vx0:
        # beside a mixed vowel: its vertical part moves to the cell's edge, then narrows to
        # the least width the designer gave that vowel; what is still missing is taken
        # from the initial
        cols = vparts[nh:]
        cr = max(p[1][2] for p in cols)
        dx = min(end + G - vx0, CELL[2] - cr)
        cols = [shift_x(p, 0, 1, dx, 1 + dx) for p in cols]
        vx0, cr = vx0 + dx, cr + dx
        if end + G > vx0:
            # narrow the vertical part, down to 75% of its width and never under ㅏ's least
            least = max(MINW.get(("V", "ㅏ"), 0), 0.75 * (cr - vx0))
            nx0 = min(end + G, cr - least)
            if nx0 > vx0:
                cols = [shift_x(p, vx0, cr, nx0, cr) for p in cols]
                vx0 = nx0
        vparts = vparts[:nh] + cols
        parts, end = initial_parts(Lc, v, hf, version, vb, vx0, hard=True)
    ROLES[:] = ["I"] * len(parts)
    if vc == 0 and end + G > vx0:
        # the initial needs more room: the vowel moves right as it is, and when the two
        # then pass the cell, both are narrowed together by one factor
        dx = end + G - vx0
        vparts = [shift_x(p, 0, 1, dx, 1 + dx) for p in vparts]
        right = max(p[1][2] for p in vparts)
        if right > CELL[2]:
            left = min(p[1][0] for p in parts)
            both = [shift_x(p, left, right, left, CELL[2]) for p in parts + vparts]
            parts, vparts = both[:len(parts)], both[len(parts):]
    if TALL[0]:
        # two bars and a stem need about 3 pens of height and two whites between: the
        # initial gives up its lower part (the final moves down by itself below)
        need = 3 * PEN + 2 * 45
        vy0 = min(p[1][1] for p in vparts); vy1 = max(p[1][3] for p in vparts)
        if vy1 - vy0 < need:
            extra = need - (vy1 - vy0)
            iy0 = min(p[1][1] for p in parts); iy1 = max(p[1][3] for p in parts)
            g = lambda y: iy1 + (y - iy1) * (iy1 - iy0 - extra) / max(iy1 - iy0, 1)
            parts = [(q[0], (q[1][0], g(q[1][1]), q[1][2], g(q[1][3]))) for q in parts]
            vparts = [(q[0], (q[1][0], q[1][1], q[1][2], q[1][3] + extra)) for q in vparts]
    if EXTRA[0]:
        rx0 = min(p[1][0] for p in parts); rx1 = max(p[1][2] for p in parts)
        hx0 = min(p[1][0] for p in vparts); hx1 = max(p[1][2] for p in vparts)
        vparts = [shift_x(p, hx0, hx1, min(hx0, rx0), max(hx1, rx1)) for p in vparts]
    three = len(comps) >= 3 and not light
    if vc == 2 and nh and (len(comps) > 1 and not light or long_h):
        # under a cluster the vowel's horizontal part spans the whole cluster, and as far
        # right as the vertical part moved, so the syllable reads as one. Drawn long (a
        # vertical-first vowel, or three initials) it runs on under the vertical part:
        # the initial reads as the consonant, the long vowel as its vowel
        hx0 = min(p[1][0] for p in vparts[:nh]); hx1 = max(p[1][2] for p in vparts[:nh])
        ix0 = min(p[1][0] for p in parts)
        moved = (vx0 - vx0_first) if vx0 is not None else 0
        cr = max(p[1][2] for p in vparts[nh:]) if len(vparts) > nh else hx1
        nx0 = min(hx0, ix0)
        # drawn long it stops at the first vertical stroke: running on between two stems
        # it would read as ㅐ's middle bar (ㅜㅣㅣ as ㅜㅐ)
        nx1 = cr if long_h else (vx0 + PEN if three else hx1 + max(moved, 0))
        vparts = [shift_x(p, hx0, hx1, nx0, nx1) for p in vparts[:nh]] + vparts[nh:]
    parts += vparts; ROLES.extend(["V"] * len(vparts))
    if T:
        Tc = T if "JONGSEONG" in unicodedata.name(T) else chr(0x11A7 + F.index(T))
        fp = final_parts(Tc, v)
        # a final keeps 35 units of white under the vowel; if it must go lower than the
        # cell allows, it is pressed instead
        vlow = min(p[1][1] for p, r in zip(parts, ROLES) if r == "V")
        ftop = max(q[1][3] for q in fp)
        if ftop > vlow - 35:
            fbot = min(q[1][1] for q in fp)
            ntop = vlow - 35
            nbot = max(CELL[1], fbot - (ftop - ntop))
            nbot = min(nbot, ntop - 0.75 * (ftop - fbot))     # pressed by a quarter at most
            f = lambda y: nbot + (y - fbot) * (ntop - nbot) / max(ftop - fbot, 1)
            fp = [(q[0], (q[1][0], f(q[1][1]), q[1][2], f(q[1][3]))) for q in fp]
        parts += fp; ROLES.extend(["F"] * len(fp))
    return parts


def draw_grid(d, parts, ox, oy, k):
    """The cell (grey) and each part's box (initial red, vowel blue, final green)."""
    T = lambda p: (ox + p[0] * k, oy + (TOP - p[1]) * k)
    a, b = T((CELL[0], CELL[3])), T((CELL[2], CELL[1]))
    d.rectangle([a, b], outline=(185, 185, 185), width=1)
    for part, role in zip(parts, ROLES):
        bx = part[1]
        a, b = T((bx[0], bx[3])), T((bx[2], bx[1]))
        d.rectangle([a, b], outline=GRID_COL[role], width=1)


def draw_parts(d, parts, ox, oy, k):
    T = lambda p: (ox + p[0] * k, oy + (TOP - p[1]) * k)
    w = PEN * k; r = w / 2

    def stroke(a, b, bend):
        Q = [T(q) for q in FR.curve(a, b, bend, n=12)]
        d.line(Q, fill=(0, 0, 0), width=int(round(w)), joint="curve")
        for c in (Q[0], Q[-1]):
            d.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r], fill=(0, 0, 0))

    for part in parts:
        if part[0] == "dot":
            b = part[1]
            c = ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
            cc = T(c); rr = PEN * 0.8 * k
            d.ellipse([cc[0] - rr, cc[1] - rr, cc[0] + rr, cc[1] + rr], fill=(0, 0, 0))
            continue
        frame, b = part
        g = FR.in_box(frame, b)
        bs = frame.get("b", [0] * len(g["s"]))
        size = max(b[2] - b[0] - PEN, b[3] - b[1] - PEN)
        for kk, (i, j) in enumerate(g["s"]):
            stroke(g["p"][i], g["p"][j], bs[kk] * size if kk < len(bs) else 0)
        for cx, cy, rx, ry in g["r"]:
            c = T((cx, cy)); ax, ay = abs(rx) * k, abs(ry) * k
            d.ellipse([c[0] - ax - r, c[1] - ay - r, c[0] + ax + r, c[1] + ay + r], fill=(0, 0, 0))
            if ax > r and ay > r:
                d.ellipse([c[0] - ax + r, c[1] - ay + r, c[0] + ax - r, c[1] + ay - r], fill=(255, 255, 255))


def original(d, ch, ox, oy, k):
    from fontTools.ttLib import TTFont
    tt = TTFont(SRC); gs, cmap = tt.getGlyphSet(), tt.getBestCmap()
    for poly in M.polygon_points(M.flattened(M.record(gs, cmap[ord(ch)]))):
        d.polygon([(ox + x * k, oy + (TOP - y) * k) for x, y in poly], fill=(0, 0, 0) if M.signed_area(poly) > 0 else (255, 255, 255))


ROWS = [
    ("현대 글자 확인: 원본 | 조합", [("orig", "쌀"), ("ㅆㅏㄹ",), ("orig", "꿈"), ("ㄲㅜㅁ",), ("orig", "땀"), ("ㄸㅏㅁ",),
                                  ("orig", "뷁"), ("ㅂㅞㄺ",), ("orig", "괢"), ("ㄱㅙㄻ",), ("orig", "뚫"), ("ㄸㅜㅀ",)]),
    ("섞인 모음 위 묶음", [("ᄣᅫᇌ",), ("ᄢᅫᆰ",), ("ᄡᅯᇌ",), ("ᄣᆀᆪ",), ("ᄧᅪᆲ",), ("ᄩᅰᆶ",), ("ᄢᅬᆪ",), ("ᄡᆢᆰ",)]),
    ("세로 + 가로", [("ᄀᅶ",), ("ᄀᅷ",), ("ᄀᅺ",), ("ᄀᅻ",), ("ᄀᅼ",), ("ᄀᆚ",), ("ᄀᆛ",), ("ᄀᆜ",), ("ᄀᆝ",), ("ᄀᆣ",), ("ᄀퟂ",), ("ᄀᆗ",)]),
    ("세로 + 가로, 복잡", [("ᄣᅶᆰ",), ("ᄡᆚᆪ",), ("ᄢᅻᆶ",), ("ᄧᆜᇌ",), ("ᄩᅽᆲ",), ("ᄡᆝᆯ",), ("ᄫᆛᆫ",), ("ᄣퟃᆰ",)]),
    ("세로 + 세로", [("ᄀᆘ",), ("ᄀᆙ",), ("ᄀᆥ",), ("ᄀힾ",), ("ᄀힿ",), ("ᄀퟀ",), ("ᄀퟄ",), ("ᄢᆘᆰ",), ("ᄡᆥᇌ",), ("ᄣힾᆪ",), ("ᄩퟄᆯ",)]),
    ("셋", [("ᄀힽ",), ("ᄀퟁ",), ("ᄀᆋ",), ("ᄀힱ",), ("ᄀힶ",), ("ᄢힽᇌ",), ("ᄣퟁᆰ",), ("ᄡᆋᆯ",), ("ᄢힱᆪ",), ("ᄣힶᇌ",)]),
    ("ㅗㅗ, ㅜㅜ (土)", [("ᄀᆂ",), ("ᄀᆍ",), ("ᄆᆂᆷ",), ("ᄃᆍᆯ",), ("ᄀᆃ",), ("ᄀᆖ",)]),
    ("ㅗㅗㅣ ‡, ㅣㅗㅣ 十", [("ᄀힱ",), ("ᄢힱᆪ",), ("ᄆힱᆫ",), ("ᄀퟁ",), ("ᄣퟁᆰ",), ("ᄆퟁᆫ",), ("ᄡퟁ",)]),
    ("여린히읗", [("ㅎㅏ",), ("ᅙᅡ",), ("ᅙᅵ",), ("ᅙᅩ",), ("ᅙᅳᆼ",), ("ᄒᆞᇙ",), ("마ᇙ",), ("ᅙᅥᆫ",)]),
]


COMPV = {"ㅘ": "ㅗㅏ", "ㅙ": "ㅗㅐ", "ㅚ": "ㅗㅣ", "ㅝ": "ㅜㅓ", "ㅞ": "ㅜㅔ", "ㅟ": "ㅜㅣ", "ㅢ": "ㅡㅣ"}
LIGHT = {"ㅂ": "ㅸ", "ㅁ": "ㅱ", "ㅍ": "ㆄ", "ㅃ": "ㅹ"}
LABEL_FONT = os.path.join(os.path.dirname(SRC), "..", "fonts", "KNPSKkomiMono-Regular.ttf")


def describe(it):
    """The syllable's slots: (initial 1-3, vowel 1-3, final 1-3) as compatibility jamo."""
    text = it[1] if it[0] == "orig" else it[0]
    if len(text) == 1:                       # a precomposed modern syllable
        n = ord(text) - 0xAC00
        text = I[n // 588] + V[n % 588 // 28] + (F[n % 28] if n % 28 else "")
    L, Vc = text[0], text[1]
    T = text[2] if len(text) > 2 else None
    Lc = L if "CHOSEONG" in unicodedata.name(L) else chr(0x1100 + I.index(L))
    comps, light = parse(Lc)
    mark = {"chi": "치", "jeong": "정"}
    if light:
        ini = [LIGHT.get(comps[0][0], comps[0][0] + "ㅇ")]
    else:
        ini = [j + mark.get(var, "") for j, var in comps]
    if Vc in V:
        vow = list(COMPV.get(Vc, Vc))
    elif "JUNGSEONG" in unicodedata.name(Vc):
        vow = []
        for t in vowel_tokens(Vc):
            vow += list(COMPV.get(t, t))
    else:
        vow = [Vc]
    fin = []
    if T:
        Tc = T if "JONGSEONG" in unicodedata.name(T) else chr(0x11A7 + F.index(T))
        fin = [j for j, _ in parse(Tc)[0]]
    return ini, vow, fin


def label(d, it, x, y, w, font):
    """Three rows (초 중 종) of three slots each; an empty slot is a dot."""
    from PIL import ImageFont
    rows = describe(it)
    lh = int(font.size * 1.45)
    for r, (name, slots) in enumerate(zip("초중종", rows)):
        yy = y + r * lh
        d.text((x, yy), name, fill=(140, 140, 140), font=font)
        sw = (w - font.size * 1.4) / 3
        for k in range(3):
            t = slots[k] if k < len(slots) else "·"
            d.text((x + font.size * 1.4 + k * sw, yy), t, fill=(0, 0, 0) if k < len(slots) else (190, 190, 190), font=font)


# reference fonts: NanumMyeongjo-YetHangul.ttf and NanumBarunGothic-YetHangul.ttf (OFL) in
# the folder NANUM_DIR, shaped with libraqm; without NANUM_DIR no reference rows
REFS = ["NanumMyeongjo-YetHangul.ttf", "NanumBarunGothic-YetHangul.ttf"]


def as_text(it):
    """The syllable as text a font can shape: precomposed if modern, else conjoining jamo."""
    if it[0] == "orig":
        return it[1]
    t = it[0]
    if len(t) == 1:
        return t
    if all(not ("CHOSEONG" in unicodedata.name(c) or "JUNGSEONG" in unicodedata.name(c) or
                "JONGSEONG" in unicodedata.name(c)) for c in t if not 0xAC00 <= ord(c) <= 0xD7A3):
        if all(c in I or c in V or c in F for c in t):       # modern, written in compatibility jamo
            i, v = I.index(t[0]), V.index(t[1])
            f = F.index(t[2]) if len(t) > 2 else 0
            return chr(0xAC00 + (i * 21 + v) * 28 + f)
    return unicodedata.normalize("NFD", t)


def main():
    """One image per row: SHEET with _0, _1, ... before the extension. Under each syllable
    its slots (초성 1-3, 중성 1-3, 종성 1-3)."""
    from PIL import ImageFont
    k = float(os.environ.get("SCALE", "0.11")); cell = int(1000 * k)
    n = int(os.environ.get("DOWN", "1"))
    for r, (title, items) in enumerate(ROWS):
        img = Image.new("RGB", (cell * len(items) + 12, int(1150 * k) + 12), "white")
        d = ImageDraw.Draw(img)
        for c, it in enumerate(items):
            ox, oy = 6 + c * cell, 6
            if it[0] == "orig" or len(it[0]) == 1:
                if os.environ.get("GRID"):
                    a, b = (ox + CELL[0] * k, oy + (TOP - CELL[3]) * k), (ox + CELL[2] * k, oy + (TOP - CELL[1]) * k)
                    d.rectangle([a, b], outline=(185, 185, 185), width=1)
                original(d, it[-1] if it[0] == "orig" else it[0], ox, oy, k); continue
            parts = syllable(it[0], it[1] if len(it) > 1 else "C")
            if os.environ.get("GRID"):
                draw_grid(d, parts, ox, oy, k)
            draw_parts(d, parts, ox, oy, k)
        if n > 1:
            img = img.resize((img.size[0] // n, img.size[1] // n), Image.LANCZOS)
        refs = os.environ.get("NANUM_DIR")
        if refs:
            em = cell / n
            fonts = [ImageFont.truetype(os.path.join(refs, f), int(em * 0.9), layout_engine=ImageFont.Layout.RAQM)
                     for f in REFS]
            rh = int(em * 1.12)
            out = Image.new("RGB", (img.size[0], img.size[1] + rh * len(fonts)), "white")
            out.paste(img, (0, 0))
            d = ImageDraw.Draw(out)
            for f_i, font in enumerate(fonts):
                for c, it in enumerate(items):
                    cx = (6 + c * cell) / n + em / 2
                    cy = img.size[1] + f_i * rh + rh / 2
                    d.text((cx, cy), as_text(it), font=font, fill=(0, 0, 0), anchor="mm")
            img = out
        if os.environ.get("LABELS", "1") == "1":
            fs = max(11, int(cell / n * 0.15))
            font = ImageFont.truetype(LABEL_FONT, fs)
            out = Image.new("RGB", (img.size[0], img.size[1] + int(3 * fs * 1.45) + 8), "white")
            out.paste(img, (0, 0))
            d = ImageDraw.Draw(out)
            for c, it in enumerate(items):
                label(d, it, (6 + c * cell) / n + 2, img.size[1] + 2, cell / n - 6, font)
            img = out
        base, ext = os.path.splitext(SHEET)
        img.save(f"{base}_{r}{ext}")

main()

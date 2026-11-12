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
        "IEUNG": "ㅇ", "CIEUC": "ㅈ", "CHIEUCH": "ㅊ", "KHIEUKH": "ㅋ", "THIEUTH": "ㅌ", "PHIEUPH": "ㅍ", "HIEUH": "ㅎ"}
SLANT = set("ㅅㅈㅊ")
DOUBLE_OF_FIRST = {"ㄱ": 1, "ㄷ": 4, "ㅂ": 8, "ㅅ": 10, "ㅈ": 13}
PEN = FR.PEN
ROLES = []
CELL = (13, -153, 844, 819)      # where 98% of the designer's syllables put their ink
TOP = 900


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


def frame_of(jamo, var=None):
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


def place_row(region, comps, singles, mins, lo, hi):
    """Boxes for components side by side, starting at the region's left. Widths are the
    region shared in proportion to the singles' widths, but never under `mins`; when that
    makes the row longer it moves left (not past lo). Returns the boxes and the row's
    right end, which may pass hi: the caller makes room (moves the vowel)."""
    x0, y0, x1, y1 = region
    gaps = [(-35 if a[0] in SLANT and b[0] in SLANT else 35) for a, b in zip(comps, comps[1:])]
    ws = np.array([s[2] - s[0] for s in singles], float)
    room = (x1 - x0) - sum(gaps)
    widths = np.maximum(room * ws / ws.sum(), np.array(mins, float))
    total = widths.sum() + sum(gaps)
    if x0 + total > hi:
        x0 = max(lo, hi - total)
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


def initial_parts(ch, v, hf, version, vb):
    """The initial's parts and its right end (the vowel moves if this passes its start)."""
    vc = H.vowel_class(v)
    comps, light = parse(ch)
    sbox = lambda j: box(("I", I.index(j), v, hf), ("I", I.index(j), vc, hf), ("I*", vc, hf))
    if light:
        j, var = comps[0]
        top, low = light_boxes(sbox(j), version)
        return [(frame_of(j, var), top), (FR.FRAMES["ㅇ"], low)], top[2]
    if len(comps) == 1:
        j, var = comps[0]
        b = sbox(j)
        return [(frame_of(j, var), b)], b[2]
    d = DOUBLE_OF_FIRST.get(comps[0][0], 1)
    region = box(("I", d, v, hf), ("I", d, vc, hf), ("I", 1, v, hf), ("I", 1, vc, hf))
    singles = [sbox(j) for j, _ in comps]
    right = (vb[0] - 30) if vc == 0 else CELL[2]      # a vowel on the right stops the initial
    region = widen(region, singles, len(comps), CELL[0] + 20, right, centred=False)
    boxes, end = place_row(region, comps, singles, [MINW.get(("I", j), 0) for j, _ in comps],
                           CELL[0] + 20, right)
    return [(frame_of(j, var), b) for (j, var), b in zip(comps, boxes)], end


def final_parts(ch, v):
    vc = H.vowel_class(v)
    comps, light = parse(ch)
    sbox = lambda j: box(("F", F.index(j), v), ("F", F.index(j), vc), ("F*", vc))
    if len(comps) == 1:
        return [(frame_of(comps[0][0]), sbox(comps[0][0]))]
    region = box(("F", 9, v), ("F", 9, vc), ("F*", vc))
    singles = [sbox(j) for j, _ in comps]
    region = widen(region, singles, len(comps), CELL[0] + 20, CELL[2] - 20, centred=True)
    boxes, _ = place_row(region, comps, singles, [MINW.get(("F", j), 0) for j, _ in comps],
                         CELL[0] + 20, CELL[2] - 20)
    return [(frame_of(j, var), b) for (j, var), b in zip(comps, boxes)]


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
        out += [VTOK[t[5:]]] * 2 if t.startswith("SSANG") else [VTOK[t]]
    return out


def jamo_part(j, b):
    return ("dot", b) if j == "ㆍ" else (FR.FRAMES[j], b)


def group_box(frame, vb, strokes):
    g = FR.in_box(frame, vb)
    pts = np.array([g["p"][i] for k in strokes for i in g["s"][k]])
    return (pts[:, 0].min() - PEN / 2, pts[:, 1].min() - PEN / 2, pts[:, 0].max() + PEN / 2, pts[:, 1].max() + PEN / 2)


def vowel_layout(ch, hf, double):
    """(modern vowel index that sets the layout, the vowel's parts, its whole box)."""
    toks = vowel_tokens(ch)
    vbox = lambda m: box(("V", V.index(m), hf, double), ("V", V.index(m), hf), ("V", V.index(m), not hf))
    if len(toks) == 1 and toks[0] in V:
        m = toks[0]; b = vbox(m)
        return V.index(m), [(FR.FRAMES[m], b)], b
    if toks == ["ㆍ"]:
        b = vbox("ㅡ")
        return V.index("ㅡ"), [("dot", b)], b
    if len(toks) == 2 and toks[0] in HOR and toks[1] not in HOR:
        h, vt = toks
        fam = "ㅗ" if h in "ㅗㅛ" else "ㅜ" if h in "ㅜㅠ" else "ㅡ" if vt == "ㅣ" else "ㅜ"
        model = MODEL.get((fam, vt in TWO, vt == "ㅣ"), "ㅝ")
        b = vbox(model)
        gh, gv = GROUPS[model]
        mf = FR.FRAMES[model]
        return V.index(model), [jamo_part(h, group_box(mf, b, gh)), jamo_part(vt, group_box(mf, b, gv))], b
    if len(toks) == 2 and toks[0] in HOR and toks[1] in HOR:
        # two horizontal vowels stacked in ㅜ's place: the first above, the second below
        b = vbox("ㅜ")
        mid = (b[1] + b[3]) / 2
        up, low = (b[0], mid + 18, b[2], b[3]), (b[0], b[1], b[2], mid - 18)
        dot = 2 * 0.8 * PEN
        if toks == ["ㆍ", "ㆍ"] and mid - 18 - b[1] < dot:
            # no room for two dots one over the other: side by side, like ‥
            cx, cy = (b[0] + b[2]) / 2, mid
            return V.index("ㅜ"), [("dot", (cx - dot - 10, cy - 1, cx - 10, cy + 1)),
                                    ("dot", (cx + 10, cy - 1, cx + dot + 10, cy + 1))], b
        return V.index("ㅜ"), [jamo_part(toks[0], up), jamo_part(toks[1], low)], b
    raise ValueError(f"vowel layout not made yet: {ch} {toks}")


def shift_x(part, x0, x1, nx0, nx1):
    """A vowel part moved from x0..x1 to nx0..nx1."""
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
    v, vparts, vb = vowel_layout(Vc, hf, double)
    parts, end = initial_parts(Lc, v, hf, version, vb)
    ROLES[:] = ["I"] * len(parts)
    if H.vowel_class(v) == 0 and end + 30 > vb[0]:
        # the initial needs more room: the vowel moves right as it is, and when the two
        # then pass the cell, both are narrowed together by one factor
        dx = end + 30 - vb[0]
        vparts = [shift_x(p, vb[0], vb[2], vb[0] + dx, vb[2] + dx) for p in vparts]
        right = vb[2] + dx
        if right > CELL[2]:
            left = min(p[1][0] for p in parts)
            both = [shift_x(p, left, right, left, CELL[2]) for p in parts + vparts]
            parts, vparts = both[:len(parts)], both[len(parts):]
    parts += vparts; ROLES.extend(["V"] * len(vparts))
    if T:
        Tc = T if "JONGSEONG" in unicodedata.name(T) else chr(0x11A7 + F.index(T))
        fp = final_parts(Tc, v)
        parts += fp; ROLES.extend(["F"] * len(fp))
    return parts


GRID_COL = {"I": (230, 120, 120), "V": (110, 150, 230), "F": (100, 180, 110)}


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
                                  ("orig", "시"), ("ㅅㅣ",), ("orig", "짜"), ("ㅉㅏ",), ("orig", "닭"), ("ㄷㅏㄺ",)]),
    ("2개, 3개 묶음", [("ᄡᆞᆯ",), ("ᄢᅳᆷ",), ("ᄣᅢ",), ("ᄠᅳᆮ",), ("ᄧᅡ",), ("ᄢᅮᆯ",), ("ᄃᆞᇌ",), ("ᄡᅵ",), ("ᄩᅥ",)]),
    ("연서 (60:40)", [("ᄫᅵ",), ("가",), ("ᄫᆡ",), ("ᄝᅵ",), ("ᅗᅥ",), ("ᄫᅳᆯ",), ("ᄫᅡᆫ",)]),
    ("치두 / 정치", [("ㅅㅣ",), ("ᄼᅵ",), ("ᄾᅵ",), ("ㅈㅏ",), ("ᅎᅡ",), ("ᅐᅡ",), ("ㅊㅣ",), ("ᅔᅵ",), ("ᅕᅵ",)]),
    ("쌍 치두 / 정치", [("ㅆㅣ",), ("ᄽᅵ",), ("ᄿᅵ",), ("ㅉㅏ",), ("ᅏᅡ",), ("ᅑᅡ",)]),
    ("복잡한 현대 글자: 원본 | 조합", [("orig", "빪"), ("ㅃㅏㄻ",), ("orig", "짧"), ("ㅉㅏㄼ",), ("orig", "뿕"), ("ㅃㅜㄺ",), ("orig", "뚫"), ("ㄸㅜㅀ",), ("orig", "떫"), ("ㄸㅓㄼ",), ("orig", "뷁"), ("ㅂㅞㄺ",), ("orig", "괢"), ("ㄱㅙㄻ",)]),
    ("복잡한 옛한글", [("ᄢᅫᇌ",), ("ᄣᆀᆪ",), ("ᄩᆒᇌ",), ("ᄡᆢᆰ",), ("ᄫᆔᆶ",), ("ᄧᆈᆲ",), ("ᄢᆢᇌ",), ("ᄣᆄᆳ",), ("ᄣᅢ",), ("ᄢᅳᆷ",)]),
    ("겹모음 (가로 + 세로)", [("ᄀᆀ",), ("ᄀᆁ",), ("ᄀᆄ",), ("ᄀᆅ",), ("ᄀᆆ",), ("ᄀᆈ",), ("ᄀᆉ",), ("ᄀᆊ",), ("ᄀᆌ",), ("ᄀᆎ",), ("ᄀᆏ",), ("ᄀᆐ",), ("ᄀᆑ",), ("ᄀᆒ",), ("ᄀᆔ",), ("ᄀᆟ",), ("ᄀᆡ",)]),
    ("겹모음 (가로 + 가로)", [("ᄀᆂ",), ("ᄀᆃ",), ("ᄀᆇ",), ("ᄀᆍ",), ("ᄀᆓ",), ("ᄀᆕ",), ("ᄀᆖ",), ("ᄀᆢ",), ("ᄀᆢᆫ",), ("ᄀᆖᆯ",), ("ᄆᆃᆷ",)]),
]


def main():
    """One image per row: SHEET with _0, _1, ... before the extension."""
    k = float(os.environ.get("SCALE", "0.11")); cell = int(1000 * k)
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
        base, ext = os.path.splitext(SHEET)
        img.save(f"{base}_{r}{ext}")

main()

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


def place_row(region, comps, singles):
    """Boxes for components side by side in region."""
    x0, y0, x1, y1 = region
    gaps = [(-35 if a[0] in SLANT and b[0] in SLANT else 35) for a, b in zip(comps, comps[1:])]
    ws = np.array([s[2] - s[0] for s in singles])
    room = (x1 - x0) - sum(gaps)
    widths = room * ws / ws.sum()
    out, x = [], x0
    for k, s in enumerate(singles):
        out.append((x, s[1], x + widths[k], s[3]))
        x += widths[k] + (gaps[k] if k < len(gaps) else 0)
    return out


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
    x0, y0, x1, y1 = region
    H = y1 - y0
    ring = (H - 35) / 2 if version == "A" else H / 3
    ring = max(ring, PEN * 1.6)
    cx = (x0 + x1) / 2
    return (x0, y0 + ring + 35, x1, y1), (cx - ring / 2, y0, cx + ring / 2, y0 + ring)


def initial_parts(ch, v, hf, version="A", vb=None):
    vc = H.vowel_class(v)
    comps, light = parse(ch)
    sbox = lambda j: box(("I", I.index(j), v, hf), ("I", I.index(j), vc, hf), ("I*", vc, hf))
    if light:
        j, var = comps[0]
        top, low = light_boxes(sbox(j), version)
        return [(frame_of(j, var), top), (FR.FRAMES["ㅇ"], low)], False
    if len(comps) == 1:
        j, var = comps[0]
        return [(frame_of(j, var), sbox(j))], False
    d = DOUBLE_OF_FIRST.get(comps[0][0], 1)
    region = box(("I", d, v, hf), ("I", d, vc, hf), ("I", 1, v, hf), ("I", 1, vc, hf))
    singles = [sbox(j) for j, _ in comps]
    right = (vb[0] - 30) if vc == 0 else 960      # a vowel on the right stops the initial
    region = widen(region, singles, len(comps), 40, right, centred=False)
    boxes = place_row(region, comps, singles)
    return [(frame_of(j, var), b) for (j, var), b in zip(comps, boxes)], True


def final_parts(ch, v):
    vc = H.vowel_class(v)
    comps, light = parse(ch)
    sbox = lambda j: box(("F", F.index(j), v), ("F", F.index(j), vc), ("F*", vc))
    if len(comps) == 1:
        return [(frame_of(comps[0][0]), sbox(comps[0][0]))]
    region = box(("F", 9, v), ("F", 9, vc), ("F*", vc))
    singles = [sbox(j) for j, _ in comps]
    region = widen(region, singles, len(comps), 40, 960, centred=True)
    boxes = place_row(region, comps, singles)
    return [(frame_of(j, var), b) for (j, var), b in zip(comps, boxes)]


OLD_VOWEL = {"ᆞ": ("ㅡ", "dot"), "ᆡ": ("ㅢ", "dotbar")}


def vowel_parts(ch, hf, double):
    if ch in OLD_VOWEL:
        model, how = OLD_VOWEL[ch]
    else:
        model, how = ch, None
    v = V.index(unicodedata.normalize("NFKC", model)) if model not in V else V.index(model)
    b = box(("V", v, hf, double), ("V", v, hf), ("V", v, not hf))
    return v, model, how, b


def syllable(text, version="A"):
    """text: initial, vowel, final (conjoining jamo, or compatibility jamo for modern)."""
    L, Vc = text[0], text[1]
    T = text[2] if len(text) > 2 else None
    hf = T is not None
    Lc = L if "CHOSEONG" in unicodedata.name(L) else chr(0x1100 + I.index(L))
    Vm = Vc if Vc in OLD_VOWEL else (Vc if Vc in V else V[ord(Vc) - 0x1161])
    # a vowel box depends on whether the initial is a cluster
    comps, light = parse(Lc)
    double = len(comps) > 1 and not light
    v, model, how, vb = vowel_parts(Vm, hf, double)
    parts = initial_parts(Lc, v, hf, version, vb)[0]
    vf = FR.FRAMES[model]
    if how == "dot":
        parts.append(("dot", vb))
    elif how == "dotbar":
        vf = dict(vf); parts.append(("dot", vb, vf))
    else:
        parts.append((vf, vb))
    if T:
        Tc = T if "JONGSEONG" in unicodedata.name(T) else chr(0x11A7 + F.index(T))
        parts += final_parts(Tc, v)
    return parts


def draw_parts(d, parts, ox, oy, k):
    T = lambda p: (ox + p[0] * k, oy + (900 - p[1]) * k)
    w = PEN * k; r = w / 2

    def stroke(a, b, bend):
        Q = [T(q) for q in FR.curve(a, b, bend, n=12)]
        d.line(Q, fill=0, width=int(round(w)), joint="curve")
        for c in (Q[0], Q[-1]):
            d.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r], fill=0)

    for part in parts:
        if part[0] == "dot":
            b = part[1]
            if len(part) == 3:                 # ㅢ with its bar turned into a dot
                g = FR.in_box(part[2], b)
                (i, j) = g["s"][0]
                c = (np.array(g["p"][i]) + np.array(g["p"][j])) / 2
                for kk, (i, j) in enumerate(g["s"][1:], 1):
                    stroke(g["p"][i], g["p"][j], 0)
            else:
                c = ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
            cc = T(c); rr = PEN * 0.8 * k
            d.ellipse([cc[0] - rr, cc[1] - rr, cc[0] + rr, cc[1] + rr], fill=0)
            continue
        frame, b = part
        g = FR.in_box(frame, b)
        bs = frame.get("b", [0] * len(g["s"]))
        size = max(b[2] - b[0] - PEN, b[3] - b[1] - PEN)
        for kk, (i, j) in enumerate(g["s"]):
            stroke(g["p"][i], g["p"][j], bs[kk] * size if kk < len(bs) else 0)
        for cx, cy, rx, ry in g["r"]:
            c = T((cx, cy)); ax, ay = abs(rx) * k, abs(ry) * k
            d.ellipse([c[0] - ax - r, c[1] - ay - r, c[0] + ax + r, c[1] + ay + r], fill=0)
            if ax > r and ay > r:
                d.ellipse([c[0] - ax + r, c[1] - ay + r, c[0] + ax - r, c[1] + ay - r], fill=255)


def original(d, ch, ox, oy, k):
    from fontTools.ttLib import TTFont
    tt = TTFont(SRC); gs, cmap = tt.getGlyphSet(), tt.getBestCmap()
    for poly in M.polygon_points(M.flattened(M.record(gs, cmap[ord(ch)]))):
        d.polygon([(ox + x * k, oy + (900 - y) * k) for x, y in poly], fill=0 if M.signed_area(poly) > 0 else 255)


ROWS = [
    ("현대 글자 확인: 원본 | 조합", [("orig", "쌀"), ("ㅆㅏㄹ",), ("orig", "꿈"), ("ㄲㅜㅁ",), ("orig", "땀"), ("ㄸㅏㅁ",),
                                  ("orig", "시"), ("ㅅㅣ",), ("orig", "짜"), ("ㅉㅏ",), ("orig", "닭"), ("ㄷㅏㄺ",)]),
    ("원본 | 조합: 쁠 쓸", [("orig", "쁠"), ("ㅃㅡㄹ",), ("orig", "쓸"), ("ㅆㅡㄹ",)]),
    ("2개, 3개 묶음", [("ᄡᆞᆯ",), ("ᄢᅳᆷ",), ("ᄣᅢ",), ("ᄠᅳᆮ",), ("ᄧᅡ",), ("ᄢᅮᆯ",), ("ᄃᆞᇌ",), ("ᄡᅵ",), ("ᄩᅥ",)]),
    ("연서 A (높이를 반씩)", [("ᄫᅵ",), ("가",), ("ᄫᆡ",), ("ᄝᅵ",), ("ᅗᅥ",), ("ᄫᅳᆯ",), ("ᄫᅡᆫ",)]),
    ("연서 B (ㅇ이 1/3)", [("ᄫᅵ", "B"), ("가",), ("ᄫᆡ", "B"), ("ᄝᅵ", "B"), ("ᅗᅥ", "B"), ("ᄫᅳᆯ", "B"), ("ᄫᅡᆫ", "B")]),
    ("치두 / 정치: ㅅ ᄼ ᄾ  ㅈ ᅎ ᅐ  ㅊ ᅔ ᅕ", [("ㅅㅣ",), ("ᄼᅵ",), ("ᄾᅵ",), ("ㅈㅏ",), ("ᅎᅡ",), ("ᅐᅡ",),
                                          ("ㅊㅣ",), ("ᅔᅵ",), ("ᅕᅵ",)]),
    ("쌍: ㅆ ᄽ ᄿ  ㅉ ᅏ ᅑ", [("ㅆㅣ",), ("ᄽᅵ",), ("ᄿᅵ",), ("ㅉㅏ",), ("ᅏᅡ",), ("ᅑᅡ",)]),
]


def main():
    """One image per row: SHEET with _0, _1, ... before the extension."""
    k = float(os.environ.get("SCALE", "0.11")); cell = int(1000 * k)
    for r, (title, items) in enumerate(ROWS):
        img = Image.new("L", (cell * len(items) + 12, int(1000 * k) + 12), 255)
        d = ImageDraw.Draw(img)
        for c, it in enumerate(items):
            ox, oy = 6 + c * cell, 6
            if it[0] == "orig" or len(it[0]) == 1:
                original(d, it[-1] if it[0] == "orig" else it[0], ox, oy, k); continue
            draw_parts(d, syllable(it[0], it[1] if len(it) > 1 else "A"), ox, oy, k)
        base, ext = os.path.splitext(SHEET)
        img.save(f"{base}_{r}{ext}")

main()

"""The same Hangul three ways: the designer's font (proportional source), the released
Mono, and the 2.0 composition. usage: compare20.py out.png"""
import os, sys
OUTP = sys.argv[1]
sys.argv = ["compose_old.py", "split_all.pkl", "prep2.pkl", "fit_r3.pkl", "unused.png"]
exec(open("compose_old.py").read().replace("\nmain()\n", "\n"))
from PIL import ImageFont

LINES = ["다람쥐 헌 쳇바퀴에 타고파", "닭 볶음탕을 끓여 먹었다", "꽃밭에 앉아 꽃잎을 본다", "읽고 싶은 책이 많습니다"]
REL = os.path.join(os.path.dirname(SRC), "..", "fonts", "KNPSKkomiMono-Regular.ttf")
up = 3; K = 0.07 * up; cell = 1000 * K


def widened(parts):
    xs = [q[1][0] for q in parts] + [q[1][2] for q in parts]
    x0, x1 = min(xs), max(xs)
    sx = min(1.6, max(1.04, 0.8 * 1000 / max(x1 - x0, 1)))
    cx = (x0 + x1) / 2
    f = lambda x: 500 + (x - cx) * sx
    g = lambda y: y * 1.04 * 1.15
    return [(q[0], (f(q[1][0]), g(q[1][1]), f(q[1][2]), g(q[1][3]))) + tuple(q[2:]) for q in parts]


lab = ImageFont.truetype(REL, 16 * up)
import pickle, numpy as np
FTD = pickle.load(open("audit_fits2.pkl", "rb")); PRA = pickle.load(open("audit_prep.pkl", "rb"))
FINAL_PEN = 78           # a round pen of about the released Regular's weight, in finished units


def designer_lines(cp):
    """The designer's own fitted centrelines of syllable cp, through the build's geometry."""
    r = FTD[cp]; b = PRA[cp]["bounds"]
    sx = min(1.6, max(1.04, 0.8 * 1000 / max(b[2] - b[0], 1))); cx = (b[0] + b[2]) / 2
    f = lambda p: (500 + (p[0] - cx) * sx, p[1] * 1.04 * 1.15)
    out = [np.array([f(q) for q in FR.curve(r["points"][i], r["points"][j], r["bends"][k], n=40)]) for k, (i, j) in enumerate(r["strokes"])]
    for cx2, cy, rx, ry in r["rings"]:
        a = np.linspace(0, 2 * np.pi, 80)
        out.append(np.array([f((cx2 + rx * np.cos(t), cy + ry * np.sin(t))) for t in a]))
    return out


def pen_lines(d, lines, ox, oy, k, w):
    for Q in lines:
        pts = [(ox + x * k, oy + (1035 - y) * k) for x, y in Q]
        d.line(pts, fill=(0, 0, 0), width=int(round(w * k)), joint="curve")
        r = w / 2 * k
        for c in (pts[0], pts[-1]):
            d.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r], fill=(0, 0, 0))


rows = [("원본 꼬미", ImageFont.truetype(SRC, int(1000 * K * 1.15))), ("배포판", ImageFont.truetype(REL, int(1000 * K))),
        ("2.0 조합 (펜 64, 잘못)", None), ("2.0 조합 (펜 78)", "pen"), ("디자이너 중심선 (펜 78)", "own")]
lh = 1.32 * 1000 * K
W = 140 * up + max(len(l) for l in LINES) * cell
img = Image.new("RGB", (int(W), int(len(rows) * (len(LINES) * lh + 40 * up))), "white")
d = ImageDraw.Draw(img)
y = 10 * up
for title, font in rows:
    d.text((10 * up, y), title, font=lab, fill=(150, 60, 60)); y += 30 * up
    for line in LINES:
        if font == "own":
            x = 140 * up
            for ch in line:
                if ch != " " and ord(ch) in FTD and FTD[ord(ch)] and "strokes" in FTD[ord(ch)]:
                    pen_lines(d, designer_lines(ord(ch)), x, y, K, FINAL_PEN)
                x += cell if ch != " " else cell / 2
        elif font == "pen":
            x = 140 * up
            for ch in line:
                if ch != " ":
                    n = ord(ch) - 0xAC00
                    t = I[n // 588] + V[n % 588 // 28] + (F[n % 28] if n % 28 else "")
                    globals()["PEN"] = FINAL_PEN; FR.PEN = FINAL_PEN
                    draw_parts(d, widened(syllable(t)), x, y + (1035 - TOP) * K, K)
                    globals()["PEN"] = 64; FR.PEN = 64
                x += cell if ch != " " else cell / 2
        elif font is not None:
            x = 140 * up
            for ch in line:
                d.text((x + cell / 2, y + 1035 * K), ch, font=font, fill=(0, 0, 0), anchor="ms")
                x += cell if ch != " " else cell / 2
        else:
            x = 140 * up
            for ch in line:
                if ch != " ":
                    n = ord(ch) - 0xAC00
                    t = I[n // 588] + V[n % 588 // 28] + (F[n % 28] if n % 28 else "")
                    draw_parts(d, widened(syllable(t)), x, y + (1035 - TOP) * K, K)
                x += cell if ch != " " else cell / 2
        y += lh
    y += 10 * up
img.resize((img.size[0] // up, img.size[1] // up), Image.LANCZOS).save(OUTP)

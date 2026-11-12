"""Original / release / 2.0 averaged frames / 2.0 the designer's own jamo, on sentences
(mostly drawn syllables) and on syllables the designer never drew.
usage: compare21.py out.png"""
import os, sys, random
OUTP = sys.argv[1]
sys.argv = ["compose_old.py", "split_all.pkl", "prep2.pkl", "fit_r3.pkl", "unused.png"]
exec(open("compose_old.py").read().replace("\nmain()\n", "\n"))
from PIL import ImageFont
import pickle
import exemplar as EX

FTD = pickle.load(open("audit_fits2.pkl", "rb")); PRA = pickle.load(open("audit_prep.pkl", "rb"))
DRAWN = PRA["_drawn"]
EXS = EX.Exemplars(FTD, DRAWN, box)
REL = os.path.join(os.path.dirname(SRC), "..", "fonts", "KNPSKkomiMono-Regular.ttf")
PENW = 78
random.seed(4)
undrawn = [chr(cp) for cp in range(0xAC00, 0xD7A4) if cp not in DRAWN]
BLOCKS = [("원본이 그린 글자가 많은 문장", ["다람쥐 헌 쳇바퀴에 타고파", "꽃밭에 앉아 꽃잎을 본다", "읽고 싶은 책이 많습니다"]),
          ("원본에 없는 글자(조합으로만 나옴)", ["".join(random.sample(undrawn, 12)), "".join(random.sample(undrawn, 12)), "".join(random.sample(undrawn, 12))])]
up = 3; K = 0.07 * up; cell = 1000 * K


def widened(parts):
    xs = [q[1][0] for q in parts] + [q[1][2] for q in parts]
    x0, x1 = min(xs), max(xs)
    sx = min(1.6, max(1.04, 0.8 * 1000 / max(x1 - x0, 1)))
    cx = (x0 + x1) / 2
    f = lambda x: 500 + (x - cx) * sx
    g = lambda y: y * 1.04 * 1.15
    return [(q[0], (f(q[1][0]), g(q[1][1]), f(q[1][2]), g(q[1][3]))) for q in parts]


def syl_parts(ch, how):
    n = ord(ch) - 0xAC00
    if how == "mean":
        return syllable(I[n // 588] + V[n % 588 // 28] + (F[n % 28] if n % 28 else ""))
    return [(fr, b) for fr, b, _ in EXS.parts_for(ord(ch))]


lab = ImageFont.truetype(REL, 15 * up)
fonts = {"src": ImageFont.truetype(SRC, int(1000 * K * 1.15)), "rel": ImageFont.truetype(REL, int(1000 * K))}
ROWS = [("원본 꼬미 (없으면 빈칸)", "src"), ("배포판", "rel"), ("2.0 평균 틀", "mean"), ("2.0 디자이너 사례", "ex")]
lh = 1.32 * 1000 * K
W = 210 * up + 13 * cell
H_ = sum(30 * up + len(ROWS) * (len(lines) * lh + 8 * up) for _, lines in BLOCKS) + 20 * up
img = Image.new("RGB", (int(W), int(H_)), "white")
d = ImageDraw.Draw(img)
y = 10 * up
for btitle, lines in BLOCKS:
    d.text((10 * up, y), btitle, font=lab, fill=(40, 40, 160)); y += 30 * up
    for title, how in ROWS:
        d.text((10 * up, y + 20 * up), title, font=lab, fill=(150, 60, 60))
        for line in lines:
            x = 210 * up
            for ch in line:
                if ch == " ":
                    x += cell / 2; continue
                if how in fonts:
                    if how == "src" and ord(ch) not in DRAWN:
                        pass
                    else:
                        d.text((x + cell / 2, y + 1035 * K), ch, font=fonts[how], fill=(0, 0, 0), anchor="ms")
                else:
                    globals()["PEN"] = PENW; FR.PEN = PENW
                    draw_parts(d, widened(syl_parts(ch, how)), x, y + (1035 - TOP) * K, K)
                    globals()["PEN"] = 64; FR.PEN = 64
                x += cell
            y += lh
        y += 8 * up
img.resize((img.size[0] // up, img.size[1] // up), Image.LANCZOS).save(OUTP)
print("ok")

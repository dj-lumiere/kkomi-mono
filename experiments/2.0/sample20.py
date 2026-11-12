"""A 2.0 sample: Hangul and old Hangul from the composer, hanja and kana from their
skeletons with the elliptical pen, Latin from the new build, mixed on one line.
usage: NOTO=NotoSansKR-VF.ttf [BUILT=font.ttf] sample20.py out.png"""
import os, sys
OUTP = sys.argv[1]
sys.argv = ["compose_old.py", "split_all.pkl", "prep2.pkl", "fit_r3.pkl", "unused.png"]
exec(open("compose_old.py").read().replace("\nmain()\n", "\n"))
from PIL import ImageFont
import numpy as np
import cjk_pen as CJ

BUILT = os.environ.get("BUILT", os.path.join(FR.ROOT, "fonts", "KNPSKkomiMono-Regular.ttf"))   # a build with HALF_TALL
LINES = [
    "꼬미 Mono 2.0: 한글, 漢字, かな, カナ, ABC 123",
    "다람쥐 헌 쳇바퀴에 타고파. 뷁 쌂 빪 꿇 닭!",
    "ᄒᆞᆫ ᄀᆞᆯ ᄫᅵ ᄢᅫᇌ ᄣퟁᆰ ᅙᅡ ᄼᅵ ᄾᅵ",
    "大韓民國 學校 愛 龍 鬱 驚 / ひらがな カタカナ",
    "fn main() -> 결과 { let 値 = \"かな\"; }",
]
up = 3; K = 0.07 * up; cell = 1000 * K; half = 500 * K
lat = ImageFont.truetype(BUILT, int(1000 * K))


def units(text):
    """Split a line into drawing units: precomposed or conjoining syllables, one char else."""
    out, i = [], 0
    while i < len(text):
        c = text[i]
        if 0x1100 <= ord(c) <= 0x115F or 0xA960 <= ord(c) <= 0xA97F:
            j = i + 1
            while j < len(text) and (0x1160 <= ord(text[j]) <= 0x11FF or 0xD7B0 <= ord(text[j]) <= 0xD7FF):
                j += 1
            out.append(text[i:j]); i = j
        else:
            out.append(c); i += 1
    return out


def wide(u):
    c = u[0]
    return len(u) > 1 or 0xAC00 <= ord(c) <= 0xD7A3 or 0x3040 <= ord(c) <= 0x30FF or 0x4E00 <= ord(c) <= 0x9FFF


def widened(parts):
    """The build's geometry for Hangul (enlarge_hangul): widened about the middle until
    the ink fills 0.8 of the two cells (at most 1.6 times), set in the middle of the
    cells. Only the boxes move: the pen keeps its width."""
    xs = [q[1][0] for q in parts] + [q[1][2] for q in parts]
    x0, x1 = min(xs), max(xs)
    sx = min(1.6, max(1.04, 0.8 * 1000 / max(x1 - x0, 1)))
    cx = (x0 + x1) / 2
    f = lambda x: 500 + (x - cx) * sx
    out = []
    for q in parts:
        b = q[1]
        g = lambda y: y * 1.04 * 1.15          # the build: Hangul 1.04, then everything TALL
        nb = (f(b[0]), g(b[1]), f(b[2]), g(b[3]))
        out.append((q[0], nb) + tuple(q[2:]))
    return out


def draw_unit(d, img, u, x, y):
    c = u[0]
    if 0xAC00 <= ord(c) <= 0xD7A3:
        n = ord(c) - 0xAC00
        t = I[n // 588] + V[n % 588 // 28] + (F[n % 28] if n % 28 else "")
        draw_parts(d, widened(syllable(t)), x, y + (1035 - TOP) * K, K)
    elif len(u) > 1:
        draw_parts(d, widened(syllable(u)), x, y + (1035 - TOP) * K, K)
    elif 0x4E00 <= ord(c) <= 0x9FFF or 0x3040 <= ord(c) <= 0x30FF:
        m, off = CJ.noto_mask(c) if ord(c) >= 0x4E00 else CJ.src_mask(c)
        lines = CJ.centrelines(m, off)
        s = 0.9
        for Q in lines:
            Q = np.column_stack([500 + (Q[:, 0] - 500) * s, (350 + (Q[:, 1] - 350) * s) * 1.15])
            CJ.stamp(d, Q, x, y, K, 64, 54, top=1035)
    else:
        d.text((x + half / 2, y + 1035 * K), c, font=lat, fill=(0, 0, 0), anchor="ms")


rows = [units(l) for l in LINES]
W = max(sum(cell if wide(u) else half for u in r) for r in rows) + 40 * up
lh = 1.32 * 1000 * K
img = Image.new("RGB", (int(W), int(len(rows) * lh + 30 * up)), "white")
d = ImageDraw.Draw(img)
y = 10 * up
for r in rows:
    x = 20 * up
    for u in r:
        if u != " ":
            draw_unit(d, img, u, x, y)
        x += cell if wide(u) else half
    y += lh
img.resize((img.size[0] // up, img.size[1] // up), Image.LANCZOS).save(OUTP)

"""Hanja (from Noto Sans KR, OFL) and kana (from the source's gothic kana) redrawn the Kkomi
way: the gothic glyph's skeleton, cut into lines (skgraph), smoothed, then drawn with the
elliptical pen. Writes three sheets: hanja, kana, and a mixed line.
usage: cjk_pen.py NotoSansKR-VF.ttf out_prefix"""
import sys, os
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import gaussian_filter1d
import frames as FR, make_mono as M, skgraph as SG
from fontTools.ttLib import TTFont

NOTO, PREFIX = (sys.argv[1:3] if __name__ == "__main__" else (os.environ.get("NOTO", ""), ""))
SRC = os.path.join(FR.ROOT, "source", "KNPSKkomi.otf")
BASE = 880            # baseline row of the 1000-unit raster (y up in units = BASE - row)


def noto_mask(ch, wght=300):
    f = ImageFont.truetype(NOTO, 1000)
    f.set_variation_by_axes([wght])
    img = Image.new("L", (1100, 1150), 0)
    ImageDraw.Draw(img).text((50, BASE), ch, font=f, fill=255, anchor="ls")
    return np.asarray(img) > 127, (-50, BASE)


def src_mask(ch):
    tt = TTFont(SRC); gs, cmap = tt.getGlyphSet(), tt.getBestCmap()
    m, off, b = FR.ink(M.polygon_points_ops(M.record(gs, cmap[ord(ch)])))
    return m, off


def centrelines(mask, off, smooth=4.0):
    g = SG.lines_of(mask, off)
    out = []
    for Q in g["lines"] + g["loops"]:
        Q = SG.resample(Q, 4.0)
        if len(Q) > 5:
            Q = np.column_stack([gaussian_filter1d(Q[:, 0], smooth, mode="nearest"),
                                 gaussian_filter1d(Q[:, 1], smooth, mode="nearest")])
        out.append(Q)
    return out


def stamp(d, Q, ox, oy, k, wx, wy, top=1000):
    rx, ry = wx / 2 * k, wy / 2 * k
    for p, q in zip(Q[:-1], Q[1:]):
        n = max(2, int(np.hypot(*(q - p)) / 3))
        for t in np.linspace(0, 1, n):
            x = ox + (p[0] + t * (q[0] - p[0])) * k; y = oy + (top - (p[1] + t * (q[1] - p[1]))) * k
            d.ellipse([x - rx, y - ry, x + rx, y + ry], fill=0)
    if len(Q) == 1:
        x = ox + Q[0][0] * k; y = oy + (top - Q[0][1]) * k
        d.ellipse([x - rx, y - ry, x + rx, y + ry], fill=0)


def grid(chars, maker, pens, path, ref=None, k=0.11, up=3):
    """Rows: the reference (gothic) if given, then the pen versions."""
    K = k * up; cell = int(1000 * K)
    rows = (1 if ref else 0) + len(pens)
    img = Image.new("L", (cell * len(chars) + 40 * up, rows * cell + 20 * up), 255)
    d = ImageDraw.Draw(img)
    lab = ImageFont.truetype(os.path.join(FR.ROOT, "fonts", "KNPSKkomiMono-Regular.ttf"), 12 * up)
    for c, ch in enumerate(chars):
        m, off = maker(ch)
        lines = centrelines(m, off)
        ox = 40 * up + c * cell
        r = 0
        if ref:
            small = Image.fromarray((m * 255).astype("uint8")).resize((int(m.shape[1] * K), int(m.shape[0] * K)))
            img.paste(0, (int(ox + off[0] * K), int(10 * up + (1000 - off[1]) * K - 120 * K)), small)
            r = 1
        for n, (name, wx, wy) in enumerate(pens):
            oy = 10 * up + (r + n) * cell - 120 * K
            for Q in lines:
                stamp(d, Q, ox, oy, K, wx, wy)
    y = 10 * up
    if ref:
        d.text((4, y + cell // 2), ref, font=lab, fill=120); y += cell
    for name, wx, wy in pens:
        d.text((4, y + cell // 2), name, font=lab, fill=120); y += cell
    img.resize((img.size[0] // up, img.size[1] // up), Image.LANCZOS).save(path)


HANJA = "一十大人水永國學愛書韓龍鬱驚靈體龜鑑"
KANA = "あいうえおかきさしすぬねのはふゆアイウエオキシツヌネノヲン"
PENS = [("400", 64, 54), ("700", 88, 66)]

if __name__ == "__main__":
    grid(HANJA, lambda ch: noto_mask(ch), PENS, PREFIX + "_hanja.png", ref="Noto")
    grid(KANA, src_mask, PENS, PREFIX + "_kana.png", ref="원본")
    print("done")

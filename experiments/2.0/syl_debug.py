import sys, pickle
ROOT = __import__("os").path.abspath(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "..", ".."))
sys.path.insert(0, ROOT + "/tools"); sys.path.insert(0, ROOT + "/experiments/2.0")
from PIL import Image, ImageDraw
from fontTools.ttLib import TTFont
import make_mono as M, hangul_fill as H, frames as FR
tt = TTFont(ROOT + "/source/KNPSKkomi.otf"); gs, cmap = tt.getGlyphSet(), tt.getBestCmap()
res = pickle.load(open(sys.argv[1], "rb"))
chars = sys.argv[2] if len(sys.argv) > 2 else None
good = FR.good
pick = [cp for cp in sorted(res) if (chars and chr(cp) in chars) or (not chars and not good(res[cp]))][:16]
k = 0.28; cell = 300; COL = ["#d22", "#16c", "#090"]
img = Image.new("RGB", (cell * 4, cell * ((len(pick) + 3) // 4)), "white"); d = ImageDraw.Draw(img)
for n, cp in enumerate(pick):
    r = res[cp]; ox, oy = (n % 4) * cell, (n // 4) * cell
    T = lambda p: (ox + 10 + p[0] * k, oy + 10 + (1000 - p[1]) * k)
    for poly in M.polygon_points(M.flattened(M.record(gs, cmap[cp]))):
        d.polygon([T(p) for p in poly], outline="#aaa")
    if "iou" not in r:
        d.text((ox + 4, oy + 2), chr(cp) + " " + r.get("error", "")[:30], fill="black"); continue
    if len(sys.argv) > 4:
        ip, ir = r["init"]
        for (i, j) in r["strokes"]:
            d.line([T(ip[i]), T(ip[j])], fill="#e8a", width=1)
        for (cx, cy, rx, ry) in ir:
            rx, ry = abs(rx), abs(ry); d.ellipse([T((cx - rx, cy + ry)), T((cx + rx, cy - ry))], outline="#e8a")
    for kk, (i, j) in enumerate(r["strokes"]):
        d.line([T(q) for q in FR.curve(r["points"][i], r["points"][j], r["bends"][kk])], fill=COL[r["owner_s"][kk]], width=3)
    for kk, (cx, cy, rx, ry) in enumerate(r["rings"]):
        rx, ry = abs(rx), abs(ry)
        a, b = T((cx - rx, cy + ry)), T((cx + rx, cy - ry)); d.ellipse([a, b], outline=COL[r["owner_r"][kk]], width=3)
    for x, y in r.get("uncovered", []):
        c = T((x, y)); d.ellipse([c[0] - 3, c[1] - 3, c[0] + 3, c[1] + 3], fill="black")
    pa = r.get("piece_along")
    if pa:
        for kk, (i, j) in enumerate(r["strokes"]):
            if pa[kk] > 25:
                d.line([T(q) for q in FR.curve(r["points"][i], r["points"][j], r["bends"][kk])], fill="#f90", width=7)
                d.line([T(q) for q in FR.curve(r["points"][i], r["points"][j], r["bends"][kk])], fill=COL[r["owner_s"][kk]], width=3)
    d.text((ox + 4, oy + 2), f"{chr(cp)} iou {r['iou']:.2f} a{r['along95']:.0f} c{r['cover95']:.0f}", fill="black")
img.save(sys.argv[3] if len(sys.argv) > 3 else "syl_debug.png")

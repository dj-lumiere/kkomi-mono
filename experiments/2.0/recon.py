"""2.0 feasibility, part 1: centreline + pen reconstruction of the drawn Hangul.
Each drawn syllable is rasterised at 1000 px per em, skeletonised, its short spurs
pruned, each skeleton path smoothed, and the paths drawn again with a round pen as wide
as the median stroke. The redraw is compared with the original by intersection over
union. Prints the distribution, and saves a sheet of the best, middle and worst."""
import sys, math, json, time, random
import numpy as np, pathops
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage
from skimage.morphology import skeletonize
from skan import Skeleton
from fontTools.ttLib import TTFont
from fontTools.pens.recordingPen import RecordingPen
SRC = sys.argv[1]; OUT = sys.argv[2]
font = ImageFont.truetype(SRC, 1000); ASC, DESC = 1100, 320
tt = TTFont(SRC); gs = tt.getGlyphSet(); cmap = tt.getBestCmap()
def drawn(cp):
    p = RecordingPen(); gs[cmap[cp]].draw(p); return bool(p.value)
def mask(ch):
    img = Image.new("L", (1100, ASC + DESC), 0)
    ImageDraw.Draw(img).text((50, ASC), ch, font=font, fill=255, anchor="ls")
    return np.array(img) > 127
def smooth(pts, sigma=6.0):
    d = np.r_[0, np.cumsum(np.hypot(*np.diff(pts, axis=0).T))]
    if d[-1] < 8: return pts
    t = np.arange(0, d[-1] + 1e-9, 4.0)
    q = np.stack([np.interp(t, d, pts[:, 0]), np.interp(t, d, pts[:, 1])], 1)
    k = max(1, int(sigma / 4))
    if len(q) > 2 * k + 1:
        sm = np.stack([ndimage.gaussian_filter1d(q[:, j], k, mode="nearest") for j in range(2)], 1)
        sm[0], sm[-1] = q[0], q[-1]
        return sm
    return q
def centrelines(m):
    dt = ndimage.distance_transform_edt(m); sk = skeletonize(m)
    if not sk.any(): return [], 0
    g = Skeleton(sk); paths = [g.path_coordinates(i) for i in range(g.n_paths)]
    r = float(np.median([dt[tuple(p)] for rc in paths for p in rc]))
    while True:
        ends = {}
        for rc in paths:
            for e in (tuple(rc[0]), tuple(rc[-1])): ends[e] = ends.get(e, 0) + 1
        keep = [rc for rc in paths if not ((ends[tuple(rc[0])] == 1) != (ends[tuple(rc[-1])] == 1) and len(rc) < 1.6 * r)]
        if len(keep) == len(paths): break
        paths = keep
    return [smooth(np.array([[c, rr] for rr, c in rc], float)) for rc in paths], r
def redraw(paths, width, shape):
    path = pathops.Path(); pen = path.getPen()
    for p in paths:
        if len(p) < 2:
            continue
        pen.moveTo(tuple(p[0]))
        for q in p[1:]: pen.lineTo(tuple(q))
        pen.endPath()
    path.stroke(width, pathops.LineCap.ROUND_CAP, pathops.LineJoin.ROUND_JOIN, 4)
    path.convertConicsToQuads()
    rec = RecordingPen(); path.draw(rec)
    img = Image.new("L", (shape[1], shape[0]), 0); d = ImageDraw.Draw(img)
    poly = []
    def flush():
        if len(poly) > 2: d.polygon(poly, fill=255)
    for op, args in rec.value:
        if op == "moveTo":
            flush(); poly = [args[0]]
        elif op in ("lineTo",):
            poly.append(args[0])
        elif op == "qCurveTo":
            p0 = poly[-1]
            pts = list(args)
            for n in range(len(pts) - 1):
                c = pts[n]; e = pts[n + 1] if n == len(pts) - 2 else ((pts[n][0] + pts[n + 1][0]) / 2, (pts[n][1] + pts[n + 1][1]) / 2)
                for t in np.linspace(0, 1, 8)[1:]:
                    poly.append(((1 - t) ** 2 * p0[0] + 2 * t * (1 - t) * c[0] + t * t * e[0], (1 - t) ** 2 * p0[1] + 2 * t * (1 - t) * c[1] + t * t * e[1]))
                p0 = e
        elif op == "closePath":
            flush(); poly = []
    flush()
    # nonzero fill: union of stroke pieces is fine to paint
    return np.array(img) > 127
cps = [cp for cp in range(0xAC00, 0xD7A4) if cp in cmap and drawn(cp)]
widths = []
for cp in random.Random(1).sample(cps, 200):
    _, r = centrelines(mask(chr(cp))); widths.append(2 * r)
W = float(np.median(widths))
print("drawn", len(cps), "pen width (median of 2r)", round(W, 1))
res = []; t0 = time.time()
for cp in cps:
    m = mask(chr(cp)); paths, r = centrelines(m)
    rd = redraw(paths, W, m.shape)
    iou = (m & rd).sum() / max(1, (m | rd).sum())
    res.append((iou, cp, len(paths)))
dt = time.time() - t0
a = np.array([x[0] for x in res])
print(f"time {dt:.0f}s ({1000*dt/len(res):.0f} ms per glyph)")
print("IoU median", round(float(np.median(a)), 3), "p10", round(float(np.percentile(a, 10)), 3), "p1", round(float(np.percentile(a, 1)), 3), "min", round(float(a.min()), 3))
res.sort()
json.dump([(round(x[0], 4), chr(x[1]), x[2]) for x in res], open(f"{OUT}/recon.json", "w"), ensure_ascii=False)
# sheet: worst 8, middle 8, best 8, original over redraw
pick = res[:8] + res[len(res) // 2 - 4: len(res) // 2 + 4] + res[-8:]
cell = 220; sheet = Image.new("RGB", (cell * 8, cell * 3), "white")
for k, (iou, cp, n) in enumerate(pick):
    m = mask(chr(cp)); paths, _ = centrelines(m); rd = redraw(paths, W, m.shape)
    rgb = np.ones(m.shape + (3,), np.uint8) * 255
    rgb[m & rd] = (40, 40, 40); rgb[m & ~rd] = (230, 80, 40); rgb[rd & ~m] = (40, 120, 230)
    im = Image.fromarray(rgb).crop((0, 100, 1100, 1300)).resize((cell, int(cell * 1200 / 1100)))
    dr = ImageDraw.Draw(im); dr.text((4, 2), f"{chr(cp)} {iou:.3f}", fill=(0, 0, 0))
    sheet.paste(im.crop((0, 0, cell, cell)), ((k % 8) * cell, (k // 8) * cell))
sheet.save(f"{OUT}/recon_sheet.png")

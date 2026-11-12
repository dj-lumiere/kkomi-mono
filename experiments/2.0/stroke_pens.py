"""Heavy weights that keep the topology of the centrelines. Two pieces (strokes, rings,
dots) that the Regular pen draws apart must stay apart at every weight, with at least
LEAST units of white (the designer's own: 3 in 4 drawn syllables keep 29 or more where
their strokes come closest). In this order:
  1. the centrelines spread across the cell first (up to 1.25 times wide),
  2. each jamo gets one pen, thinned as far as its pairs need (never under 45% of the
     target),
  3. no jamo's pen is under 2/3 of another's in the same syllable (the heavier ones
     come down instead), so a syllable keeps one colour.
usage: stroke_pens.py out.png"""
import os, sys
OUTP = sys.argv[1]
sys.argv = ["compose_old.py", "split_all.pkl", "prep2.pkl", "fit_r3.pkl", "unused.png"]
exec(open("compose_old.py").read().replace("\nmain()\n", "\n"))
from PIL import ImageFont
import numpy as np

TEXT = ["ᄢᅫᇌ", "ᄣᆀᆪ", "ᄡᆢᆰ", "ᄩᆒᇌ", "ᄢힽᇌ", "ᄧᆈᆲ", "ᄒᆞᇙ", "ᄀힱ", "ᄣퟁᆰ", "ㅃㅞㄺ", "ㅂㅣㄻ", "ㄲㅜㅀ", "ㅆㅏㄻ", "ㄷㅏㄺ"]
REGULAR = 64        # the Regular pen in source units
TOUCH = REGULAR + 10    # pieces this close already touch at Regular: joined by design
LEAST = 29          # least white between pieces kept apart (the drawn syllables' 25th percentile)


def pieces(parts, pen):
    """[(points (n, 2), closed, part, point ids)] of a laid-out syllable."""
    out = []
    for n, part in enumerate(parts):
        if part[0] == "dot":
            b = part[1]
            out.append((np.array([((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)]), False, n, set(), "dot"))
            continue
        frame, b = part
        g = FR.in_box(frame, b)
        bs = frame.get("b", [0] * len(g["s"]))
        size = max(b[2] - b[0] - PEN, b[3] - b[1] - PEN)
        for kk, (i, j) in enumerate(g["s"]):
            Q = FR.curve(g["p"][i], g["p"][j], bs[kk] * size if kk < len(bs) else 0, n=24)
            out.append((np.asarray(Q), False, n, {(n, i), (n, j)}, "stroke"))
        for cx, cy, rx, ry in g["r"]:
            a = np.linspace(0, 2 * np.pi, 48)
            out.append((np.column_stack([cx + abs(rx) * np.cos(a), cy + abs(ry) * np.sin(a)]), True, n, set(), "ring"))
    return out


def spread(ps, target, most=1.25):
    """Centrelines widened about their middle until the ink fills the cell's width."""
    xs = np.concatenate([Q[:, 0] for Q, *_ in ps])
    x0, x1 = xs.min(), xs.max()
    room = (CELL[2] - CELL[0]) - target
    f = min(most, max(1.0, room / max(x1 - x0, 1)))
    if f == 1.0:
        return ps
    mid, cmid = (x0 + x1) / 2, (CELL[0] + CELL[2]) / 2
    out = []
    for Q, closed, part, ids, kind in ps:
        Q = Q.copy(); Q[:, 0] = cmid + (Q[:, 0] - mid) * f
        out.append((Q, closed, part, ids, kind))
    return out


def pens_for(ps, target):
    """A pen per jamo (part), as wide as the target allows without new contacts."""
    parts = sorted({p[2] for p in ps})
    w = {q: float(target) for q in parts}
    pairs = []
    for a in range(len(ps)):
        for b in range(a + 1, len(ps)):
            if ps[a][3] & ps[b][3]:
                continue                        # they share a point of their frame
            A, B = ps[a][0], ps[b][0]
            d = np.hypot(A[:, None, 0] - B[None, :, 0], A[:, None, 1] - B[None, :, 1]).min()
            if d < TOUCH:
                continue                        # they already meet at Regular
            pairs.append((ps[a][2], ps[b][2], d))
    floor = 0.45 * target
    for _ in range(30):
        changed = False
        for pa, pb, d in pairs:
            over = (w[pa] + w[pb]) / 2 + LEAST - d
            if over > 0.5:
                for q in {pa, pb}:
                    w[q] = max(floor, w[q] - (over if pa == pb else over))
                changed = True
        if not changed:
            break
    low = min(w.values())
    for q in w:
        w[q] = min(w[q], 1.5 * low)
    return np.array([w[p[2]] for p in ps])


def draw_pieces(d, ps, w, ox, oy, k):
    T = lambda p: (ox + p[0] * k, oy + (TOP - p[1]) * k)
    for (Q, closed, _, _, kind), pen in zip(ps, w):
        r = pen / 2 * k
        if kind == "dot":
            c = T(Q[0]); rr = 0.8 * pen * k
            d.ellipse([c[0] - rr, c[1] - rr, c[0] + rr, c[1] + rr], fill=(0, 0, 0)); continue
        pts = [T(q) for q in Q]
        d.line(pts, fill=(0, 0, 0), width=max(1, int(round(pen * k))), joint="curve")
        for c in pts:
            d.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r], fill=(0, 0, 0))


def violates(ps, pen):
    """Some pieces drawn apart at Regular would come closer than LEAST at this pen."""
    for a in range(len(ps)):
        for b in range(a + 1, len(ps)):
            if ps[a][3] & ps[b][3]:
                continue
            A, B = ps[a][0], ps[b][0]
            d = np.hypot(A[:, None, 0] - B[None, :, 0], A[:, None, 1] - B[None, :, 1]).min()
            if TOUCH <= d < pen + LEAST:
                return True
    return False


STEMS = {400: 82, 700: 112, 800: 130, 900: 150}
rows = [(f"{w}", st) for w, st in STEMS.items()]
k = 0.12; cell = int(1000 * k)
img = Image.new("RGB", (cell * len(TEXT) + 130, (cell + 16) * len(rows) + 20), "white")
d = ImageDraw.Draw(img)
lab = ImageFont.truetype(LABEL_FONT, 13)
for r, (title, st) in enumerate(rows):
    y = 10 + r * (cell + 16)
    d.text((4, y + cell // 2 - 8), title, font=lab, fill=(110, 110, 110))
    target = 64 * st / 82
    for c, t in enumerate(TEXT):
        parts = syllable(t)
        ps = pieces(parts, target)
        pen = target
        # up to 700 the pen alone; at 800 and 900 a syllable whose strokes would close up
        # is drawn at 700 instead
        if st > 112 and violates(ps, target):
            pen = 64 * 112 / 82
            d.text((130 + c * cell + 4, y + cell + 1), "→700", font=lab, fill=(150, 60, 60))
        draw_pieces(d, ps, np.full(len(ps), pen), 130 + c * cell, y, k)
img.save(OUTP)

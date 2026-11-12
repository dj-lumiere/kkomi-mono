"""Sheets of the 2.0-composed syllables each check flags (composed, the original or the
current build in grey behind). usage: audit2_sheet.py audit2.json audit_prep_glyphs.pkl prefix"""
import sys, json, pickle, random
JS, GL, PREFIX = sys.argv[1:4]
sys.argv = ["compose_old.py", "split_all.pkl", "prep2.pkl", "fit_r3.pkl", "unused.png"]
exec(open("compose_old.py").read().replace("\nmain()\n", "\n"))
A = json.load(open(JS)); G = pickle.load(open(GL, "rb"))
random.seed(0)
k = 0.1; cell = int(1000 * k); cols = 16
lab = ImageFont.truetype(LABEL_FONT, 12) if "ImageFont" in globals() else None
from PIL import ImageFont
lab = ImageFont.truetype(LABEL_FONT, 12)


def sheet(chars, path):
    rows = (len(chars) + cols - 1) // cols
    img = Image.new("RGB", (cols * cell + 8, rows * (cell + 16) + 8), "white")
    d = ImageDraw.Draw(img)
    for n, ch in enumerate(chars):
        ox, oy = 4 + (n % cols) * cell, 4 + (n // cols) * (cell + 16)
        m, off, _ = FR.ink(G[ord(ch)])
        small = Image.fromarray((m * 255).astype("uint8")).resize((max(1, int(m.shape[1] * k)), max(1, int(m.shape[0] * k))), Image.LANCZOS)
        img.paste(Image.new("RGB", small.size, (205, 205, 205)), (int(ox + off[0] * k), int(oy + (TOP - off[1]) * k)), small)
        i, v, f = H.decompose(ord(ch))
        draw_parts(d, syllable(I[i] + V[v] + (F[f] if f else "")), ox, oy, k)
        d.text((ox + 2, oy + cell), ch + " " + ",".join(A["flags"].get(ch, [])), font=lab, fill=(150, 60, 60))
    img.save(path)


for c in ["cell", "white", "narrow", "far"]:
    pool = [ch for ch, f in A["flags"].items() if c in f]
    if c == "far":
        pool = sorted(pool, key=lambda ch: -A["far"][ch])[:16] + random.sample(pool, min(16, len(pool)))
    else:
        pool = random.sample(pool, min(32, len(pool)))
    sheet(pool, f"{PREFIX}_{c}.png")
    print(c, len(pool))

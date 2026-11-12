"""Sheets of flagged syllables, one per check: the built ones it flags (up to N, at random)
and, for comparison, the drawn ones it flags too.
usage: audit_sheet.py audit.json audit_prep_glyphs.pkl out_prefix [N]"""
import sys, json, pickle, random
from PIL import Image, ImageDraw, ImageFont
import frames as FR
import make_mono as M

LABEL = __import__("os").path.join(FR.ROOT, "fonts", "KNPSKkomiMono-Regular.ttf")


def sheet(chars, glyphs, path, k=0.1, cols=16, drawn=()):
    cell = int(1000 * k); lab = 18
    rows = (len(chars) + cols - 1) // cols
    img = Image.new("RGB", (cols * cell + 8, max(rows, 1) * (cell + lab) + 8), "white")
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(LABEL, 13)
    for n, (ch, why) in enumerate(chars):
        ox, oy = 4 + (n % cols) * cell, 4 + (n // cols) * (cell + lab)
        d.rectangle([ox + 1, oy + 1, ox + cell - 2, oy + cell - 2], outline=(225, 225, 225))
        col = (150, 0, 0) if ch in drawn else (0, 0, 0)
        # the ink as the font renders it (overlaps joined, holes by winding), scaled down
        m, off, _ = FR.ink(glyphs[ord(ch)])
        small = Image.fromarray((m * 255).astype("uint8")).resize(
            (max(1, int(m.shape[1] * k)), max(1, int(m.shape[0] * k))), Image.LANCZOS)
        img.paste(Image.new("RGB", small.size, col), (int(ox + off[0] * k), int(oy + (900 - off[1]) * k)), small)
        d.text((ox + 2, oy + cell), why, fill=(90, 90, 90), font=font)
    img.save(path)


def main(js, gl, prefix, n=48):
    A = json.load(open(js)); G = pickle.load(open(gl, "rb"))
    drawn = set(A["drawn"])
    random.seed(0)
    for check in A["summary"]:
        built = [c for c, f in A["flags"].items() if check in f and c not in drawn]
        dr = [c for c, f in A["flags"].items() if check in f and c in drawn]
        pick = random.sample(built, min(n, len(built))) + random.sample(dr, min(n // 4, len(dr)))
        sheet([(c, c + " " + ",".join(A["flags"][c])) for c in pick], G, f"{prefix}_{check}.png", drawn=drawn)
        print(check, len(built), "built,", len(dr), "drawn ->", f"{prefix}_{check}.png")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else 48)

#!/usr/bin/env python3
"""Builds one weight of a fixed-width font from a light base (make_mono_static.py makes
the base upright, make_italic.py its italic).

Every stroke is thickened by the same amount (the FreeType embolden method), and each
glyph is moved back so it stays centred in its cells. Flat strokes grow a quarter less
than upright ones, so counters stay open. Glyphs that must meet the cell edges (box
drawing, blocks, braille, Powerline) are left as they are: thicker, they would spill
out of the cell.

The weights aim at a stem of about 12.5 percent of the cap height for Regular (400)
and 17.5 percent for Bold (700).

Usage: make_bold.py <base.ttf> <out.ttf> <Regular|Italic|Bold|Bold Italic>
"""
import os
import sys

from fontTools.ttLib import TTFont
from fontTools.ttLib.removeOverlaps import removeOverlaps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_mono as M  # noqa: E402
from make_mono_static import embolden, to_tt_glyph_quadratic  # noqa: E402

# style -> (added to upright strokes, added to flat strokes, weight class)
WEIGHTS = {
    "Regular": (12, 9, 400),
    "Italic": (12, 9, 400),
    "Bold": (43, 32, 700),
    "Bold Italic": (43, 32, 700),
}
KEEP_RANGES = [(0x2500, 0x259F), (0x2800, 0x28FF), (0xE0A0, 0xE0B3)]


def main():
    src, out, style = sys.argv[1], sys.argv[2], sys.argv[3]
    GROW_X, GROW_Y, weight_class = WEIGHTS[style]
    font = TTFont(src)
    gs = font.getGlyphSet()
    cmap = font.getBestCmap()
    glyf, hmtx = font["glyf"], font["hmtx"]
    keep = {name for cp, name in cmap.items() if any(a <= cp <= b for a, b in KEEP_RANGES)}

    changed = []
    for name in font.getGlyphOrder():
        if name in keep:
            continue
        ops = M.record(gs, name)
        if M.bounds(ops) is None:
            continue
        thick = embolden(ops, GROW_X, GROW_Y)
        # embolden grows a glyph towards the upper right: move it back by half
        thick = M.transformed(thick, 1.0, -GROW_X / 2, 1.0, -GROW_Y / 2)
        glyf[name] = to_tt_glyph_quadratic(thick)
        changed.append(name)
    removeOverlaps(font, glyphNames=changed, removeHinting=True, ignoreErrors=True)
    for name in changed:
        g = glyf[name]
        g.recalcBounds(glyf)
        hmtx[name] = (hmtx[name][0], getattr(g, "xMin", 0) if g.numberOfContours else 0)

    italic = "Italic" in style
    bold = "Bold" in style
    os2 = font["OS/2"]
    os2.usWeightClass = weight_class
    # fsSelection: italic 0x01, bold 0x20, regular 0x40
    os2.fsSelection = (os2.fsSelection & ~0x61) | (0x01 if italic else 0) | (0x20 if bold else 0) \
        | (0x40 if not (bold or italic) else 0)
    font["head"].macStyle = (0x01 if bold else 0) | (0x02 if italic else 0)
    ps_style = style.replace(" ", "")
    for rec in font["name"].names:
        text = rec.toUnicode()
        if rec.nameID == 2:
            rec.string = style
        elif rec.nameID in (3, 6):
            for old in ("-Regular", "-Italic"):
                if old in text:
                    text = text.replace(old, "-" + ps_style)
                    break
            rec.string = text
        elif rec.nameID == 4:
            base = text.replace(" Regular", "").replace(" Italic", "")
            rec.string = base if style == "Regular" else f"{base} {style}"
        elif rec.nameID == 17:
            rec.string = style
    font.save(out)
    print("wrote", out)


if __name__ == "__main__":
    main()

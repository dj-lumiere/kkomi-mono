"""Captures hangul_fill's own split of every drawn syllable into initial, vowel and final
contours (and which splits it trusts), for the frame fits.
usage: split_capture.py SOURCE.otf split_all.pkl   (run from tools/)"""
import sys, pickle
sys.path.insert(0, ".")
from fontTools.ttLib import TTFont
import make_mono_static as MS, hangul_fill as H
tt = TTFont(sys.argv[1]); gs, cmap = tt.getGlyphSet(), tt.getBestCmap()
cap = {}
orig = H.learn_boxes


def grab(drawn, sp, trusted):
    cap["sp"] = {cp: sp[cp] for cp in drawn if cp in sp}
    cap["tr"] = {cp for cp in drawn if trusted(cp)}
    return orig(drawn, sp, trusted)


H.learn_boxes = grab
H.fill(gs, cmap, MS.embolden, learn=True)
H.learn_boxes = orig
pickle.dump(cap, open(sys.argv[2], "wb"))
print(len(cap["sp"]), "drawn syllables,", len(cap["tr"]), "trusted")

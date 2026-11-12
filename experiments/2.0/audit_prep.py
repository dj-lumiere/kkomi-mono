"""The 11,172 modern syllables as the current build makes them (the designer's drawn
ones, and hangul_fill's built ones for the rest), in the source's coordinates, prepared
for the frame fit like prep.py: skeleton points, holes, half-resolution ink, lines.
usage: audit_prep.py out.pkl"""
import os
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
import sys, pickle, time
from multiprocessing import Pool
import numpy as np
from skimage.morphology import skeletonize
import frame_prep as PP                  # holes_of, NPTS, and the tools path
import make_mono as M, make_mono_static as MS, hangul_fill as H, frames as FR, skgraph as SG
from fontTools.ttLib import TTFont

GLYPHS = {}


def one(cp):
    cs = GLYPHS[cp]
    m, off, b = FR.ink(cs)
    rc = np.argwhere(skeletonize(m))
    n = min(len(rc), max(len(rc) // 3, 1), PP.NPTS)
    rc = rc[np.sort(np.random.default_rng(0).choice(len(rc), n, replace=False))]
    P = np.column_stack([off[0] + rc[:, 1], off[1] - rc[:, 0]]).astype(float)
    half = m[::2, ::2]
    return cp, {"P": P, "holes": PP.holes_of(m, off), "off": off, "shape": half.shape,
                "ink": np.packbits(half), "lines": SG.lines_of(m, off)["lines"], "bounds": b}


if __name__ == "__main__":
    t0 = time.time()
    tt = TTFont(PP.SRC); gs, cmap = tt.getGlyphSet(), tt.getBestCmap()
    filled, stats = H.fill(gs, cmap, MS.embolden)
    print("fill", dict(stats), f"{time.time() - t0:.0f}s")
    drawn = set()
    for cp in range(H.BASE, H.BASE + 11172):
        name = cmap.get(cp)
        if name in filled:
            GLYPHS[cp] = M.polygon_points_ops(filled[name])
        elif name and M.bounds(M.record(gs, name)) is not None:
            GLYPHS[cp] = M.polygon_points_ops(M.record(gs, name)); drawn.add(cp)
    print(len(GLYPHS), "syllables,", len(drawn), "drawn")
    with Pool(6) as pool:
        out = dict(pool.imap_unordered(one, sorted(GLYPHS), chunksize=16))
    out["_drawn"] = drawn
    pickle.dump(out, open(sys.argv[1], "wb"))
    pickle.dump({cp: GLYPHS[cp] for cp in GLYPHS}, open(os.path.splitext(sys.argv[1])[0] + "_glyphs.pkl", "wb"))
    print(f"done in {time.time() - t0:.0f}s")

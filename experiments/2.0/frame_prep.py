"""Everything a frame fit reads from a drawn syllable, computed once: skeleton points (at
most 300, drawn at random), the holes of the ink, and the ink at half resolution (for IoU).
usage: prep.py out.pkl"""
import sys, pickle, time
from multiprocessing import Pool
ROOT = __import__("os").path.abspath(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "..", ".."))
sys.path.insert(0, ROOT + "/tools")
import numpy as np
from scipy import ndimage
from skimage.morphology import skeletonize
from fontTools.ttLib import TTFont
import make_mono as M, hangul_fill as H, frames as FR

SRC = ROOT + "/source/KNPSKkomi.otf"
NPTS = 300


def holes_of(m, off):
    lab, n = ndimage.label(~m)
    edge = set(lab[0]) | set(lab[-1]) | set(lab[:, 0]) | set(lab[:, -1])
    out = []
    for k, sl in enumerate(ndimage.find_objects(lab), 1):
        if k in edge or sl is None:
            continue
        rr, cc = np.nonzero(lab[sl] == k)
        if len(rr) < 150:
            continue
        rr = rr + sl[0].start; cc = cc + sl[1].start
        out.append((off[0] + cc.mean(), off[1] - rr.mean(), (np.ptp(cc) + 1) / 2, (np.ptp(rr) + 1) / 2))
    return out


def prep(cp):
    tt = TTFont(SRC); gs, cmap = tt.getGlyphSet(), tt.getBestCmap()
    cs = M.polygon_points_ops(M.record(gs, cmap[cp]))
    m, off, b = FR.ink(cs)
    rc = np.argwhere(skeletonize(m))
    n = min(len(rc), max(len(rc) // 3, 1), NPTS)
    rc = rc[np.sort(np.random.default_rng(0).choice(len(rc), n, replace=False))]
    P = np.column_stack([off[0] + rc[:, 1], off[1] - rc[:, 0]]).astype(float)
    half = m[::2, ::2]
    return cp, {"P": P, "holes": holes_of(m, off), "off": off, "shape": half.shape,
                "ink": np.packbits(half)}


if __name__ == "__main__":
    tt = TTFont(SRC); cmap = tt.getBestCmap(); gs = tt.getGlyphSet()
    cps = [cp for cp in range(H.BASE, H.BASE + 11172) if cp in cmap and M.bounds(M.record(gs, cmap[cp])) is not None]
    t0 = time.time()
    with Pool(6) as pool:
        out = dict(pool.imap_unordered(prep, cps, chunksize=16))
    pickle.dump(out, open(sys.argv[1], "wb"))
    print(f"{len(out)} syllables in {time.time() - t0:.0f}s")

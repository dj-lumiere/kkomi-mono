"""The skeleton of a drawn syllable as lines: stroke candidates that a frame's strokes
can be matched to one for one.

1. The skeleton's branches (between ends and junctions), short spurs at junctions removed,
   junctions a few units apart taken as one.
2. Each branch cut where it turns sharply (a corner of ㄱ, ㄷ, ㅁ).
3. At a junction, two pieces that run on straight through it are one line (ㅏ's stem
   through its bar, ㅂ's side through its middle bar).
A closed branch without junctions is a loop (ㅇ, the ring of ㅎ) and is kept apart.

lines_of(mask, off) -> {"lines": [array (n, 2) font units], "loops": [array]}
"""
import math
import numpy as np
from skan import Skeleton, summarize
from skimage.morphology import skeletonize

SPUR = 40          # a branch from a junction to an end shorter than this is a spur
NEAR = 30          # junctions closer than this are one junction
TURN = 50.0        # degrees of turn (over ±WIN units) that make a corner
WIN = 30.0
STRAIGHT = 140.0   # two pieces at a junction whose directions are this far apart run on


def resample(Q, step=5.0):
    d = np.r_[0, np.cumsum(np.hypot(*np.diff(Q, axis=0).T))]
    if d[-1] < step:
        return Q.copy()
    s = np.arange(0, d[-1], step)
    s = np.r_[s, d[-1]]
    return np.column_stack([np.interp(s, d, Q[:, 0]), np.interp(s, d, Q[:, 1])])


def heading(v):
    return math.atan2(v[1], v[0])


def corners(Q, step=5.0):
    """Indices of resampled Q where it turns by more than TURN degrees."""
    k = int(WIN / step)
    if len(Q) < 2 * k + 3:
        return []
    turn = np.zeros(len(Q))
    for i in range(k, len(Q) - k):
        a, b = Q[i] - Q[i - k], Q[i + k] - Q[i]
        t = abs(math.degrees((heading(b) - heading(a) + math.pi) % (2 * math.pi) - math.pi))
        turn[i] = t
    out = []
    for i in np.argsort(-turn):
        if turn[i] < TURN:
            break
        if all(abs(i - j) > 2 * k for j in out):
            out.append(int(i))
    return sorted(out)


def lines_of(mask, off):
    sk = skeletonize(mask)
    if sk.sum() < 5:
        return {"lines": [], "loops": []}
    skel = Skeleton(sk)
    df = summarize(skel, separator="_")
    to_font = lambda rc: np.column_stack([off[0] + rc[:, 1], off[1] - rc[:, 0]]).astype(float)
    br = []   # [src, dst, coords]
    for i in range(skel.n_paths):
        br.append([int(df.node_id_src[i]), int(df.node_id_dst[i]), to_font(skel.path_coordinates(i))])

    # union-find over node ids, for joined junctions
    parent = {}
    find = lambda a: a if parent.get(a, a) == a else find(parent[a])

    def degree():
        deg = {}
        for s, d, _ in br:
            deg[find(s)] = deg.get(find(s), 0) + 1
            deg[find(d)] = deg.get(find(d), 0) + 1
        return deg

    length = lambda Q: float(np.hypot(*np.diff(Q, axis=0).T).sum()) if len(Q) > 1 else 0.0
    for _ in range(3):
        changed = False
        deg = degree()
        # spurs
        keep = []
        for s, d, Q in br:
            a, b = deg[find(s)], deg[find(d)]
            if find(s) != find(d) and min(a, b) == 1 and max(a, b) >= 3 and length(Q) < SPUR:
                changed = True
                continue
            keep.append([s, d, Q])
        br = keep
        # close junctions
        deg = degree()
        keep = []
        for s, d, Q in br:
            if find(s) != find(d) and deg[find(s)] >= 3 and deg[find(d)] >= 3 and length(Q) < NEAR:
                parent[find(s)] = find(d)
                changed = True
                continue
            keep.append([s, d, Q])
        br = keep
        # nodes of degree 2: join their two branches
        deg = degree()
        for n, k in list(deg.items()):
            if k != 2:
                continue
            ends = [(j, e) for j, (s, d, Q) in enumerate(br) for e, x in ((0, s), (1, d)) if find(x) == n]
            if len(ends) != 2 or ends[0][0] == ends[1][0]:
                continue
            (j1, e1), (j2, e2) = ends
            s1, d1, Q1 = br[j1]; s2, d2, Q2 = br[j2]
            A = Q1 if e1 == 1 else Q1[::-1]          # ends at n
            B = Q2 if e2 == 0 else Q2[::-1]          # starts at n
            na = d1 if e1 == 0 else s1               # A's far node
            nb = d2 if e2 == 1 else s2
            br[j1] = [na, nb, np.vstack([A, B])]
            del br[j2]
            changed = True
            break
        if not changed:
            break

    deg = degree()
    loops = [Q for s, d, Q in br if find(s) == find(d) and deg[find(s)] == 2]
    br = [[s, d, Q] for s, d, Q in br if not (find(s) == find(d) and deg[find(s)] == 2)]

    # pieces: branches cut at corners. piece = [node_a, node_b, coords]
    pieces, corner_id = [], [10 ** 9]
    for s, d, Q in br:
        R = resample(Q)
        cuts = corners(R)
        nodes = [find(s)]
        for _ in cuts:
            corner_id[0] += 1; nodes.append(corner_id[0])
        nodes.append(find(d))
        idx = [0] + cuts + [len(R) - 1]
        for k in range(len(idx) - 1):
            pieces.append([nodes[k], nodes[k + 1], R[idx[k]:idx[k + 1] + 1]])

    # at each junction, join pieces that run on straight through it
    def out_dir(P, at_start):
        Q = P if at_start else P[::-1]
        d = np.r_[0, np.cumsum(np.hypot(*np.diff(Q, axis=0).T))]
        j = min(np.searchsorted(d, 40.0), len(Q) - 1)
        return Q[j] - Q[0]

    merged = True
    while merged:
        merged = False
        deg = {}
        for a, b, _ in pieces:
            deg[a] = deg.get(a, 0) + 1; deg[b] = deg.get(b, 0) + 1
        for n, k in deg.items():
            if k < 3:
                continue
            ends = [(j, e) for j, (a, b, Q) in enumerate(pieces) for e, x in ((0, a), (1, b)) if x == n]
            best = None
            for x in range(len(ends)):
                for y in range(x + 1, len(ends)):
                    (j1, e1), (j2, e2) = ends[x], ends[y]
                    if j1 == j2:
                        continue
                    u = out_dir(pieces[j1][2], e1 == 0); v = out_dir(pieces[j2][2], e2 == 0)
                    ang = math.degrees(math.acos(np.clip(u @ v / (np.hypot(*u) * np.hypot(*v) + 1e-9), -1, 1)))
                    if ang > STRAIGHT and (best is None or ang > best[0]):
                        best = (ang, j1, e1, j2, e2)
            if best:
                _, j1, e1, j2, e2 = best
                a1, b1, Q1 = pieces[j1]; a2, b2, Q2 = pieces[j2]
                A = Q1 if e1 == 1 else Q1[::-1]
                B = Q2 if e2 == 0 else Q2[::-1]
                fa = a1 if e1 == 1 else b1
                fb = b2 if e2 == 0 else a2
                # the junction stays a node of the line's other pieces: mark it by a fresh id
                pieces[j1] = [fa, fb, np.vstack([A, B[1:]])]
                del pieces[j2]
                merged = True
                break
    return {"lines": [Q for _, _, Q in pieces if length(Q) >= 20], "loops": loops}

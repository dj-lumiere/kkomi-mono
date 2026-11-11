"""2.0 experiment: every Hangul syllable put together from one shared set of parts.

From the syllables the designer drew (those that split cleanly into initial, vowel and
final), one representative part is chosen for each place:
  vowel    for each vowel, with and without a final          (21 x 2)
  initial  for each initial, vowel, with and without a final (19 x 21 x 2)
  final    for each final and vowel                          (27 x 21)
The representative is the drawn instance whose box is nearest the median box of all
instances of that part. Every syllable, drawn or not, is then built from these parts at
the places they were drawn, so:
  1. syllables that differ only in their final share the same upper part (흑 흙),
  2. a vowel stands in the same place whatever the initial (회 희),
  3. a final stands in the same place across a vowel's row.
Collisions are settled without breaking these: an initial too wide for the vowel is
narrowed, and a final too close to the strokes above is moved down by the same amount
for every initial over that vowel.

compose(glyph_set, cmap, weight) -> ({glyph name: outline}, stats). Missing parts are
borrowed from the nearest vowel of the same kind, as in hangul_fill.
"""
import collections
import sys

sys.path.insert(0, "/home/lumi/programming/RiderProjects/LumiFoundry/fonts/kkomi-mono/tools")
import make_mono as M
import hangul_fill as H

GAP_SIDE = 40     # least gap between the initial and an upright vowel stroke
GAP_ABOVE = 40    # least gap between the initial and a flat vowel under it
CLEAR = 45        # least gap between the final and the strokes above it


def capture(glyph_set, cmap, weight):
    cap = {}
    orig = H.learn_boxes

    def grab(drawn, split_parts, trusted):
        cap["drawn"] = drawn
        cap["parts"] = {cp: split_parts[cp] for cp in drawn if trusted(cp)}
        return orig(drawn, split_parts, trusted)

    H.learn_boxes = grab
    try:
        H.fill(glyph_set, cmap, weight, learn=True)
    finally:
        H.learn_boxes = orig
    return cap["drawn"], cap["parts"]


def box(cs):
    return M.bounds(H.flatten(cs))


def medoid(items):
    """The (key, contours) whose box is nearest the median box."""
    boxes = [box(cs) for _, cs in items]
    med = [sorted(b[k] for b in boxes)[len(boxes) // 2] for k in range(4)]
    best = min(range(len(items)), key=lambda n: sum(abs(boxes[n][k] - med[k]) for k in range(4)))
    return items[best]


def split_vowel(vowel, upper_h):
    """The upright and flat contours of a vowel part: upright ones run through more than
    half the height of the whole upper part (initial and vowel)."""
    tall = [q for q in vowel if M.bounds(q)[3] - M.bounds(q)[1] > 0.5 * upper_h]
    flat = [q for q in vowel if not any(q is t for t in tall)]
    return tall, flat


def sound(i_cs, v_cs, v):
    """A split worth learning from: the vowel has the parts its kind needs (an upright
    stroke for ㅏ-like vowels, a flat one for ㅗ-like ones, both for ㅘ-like ones) and the
    initial keeps clear of them (it did not take the ㅗ along)."""
    if not i_cs or not v_cs:
        return False
    ub = box(i_cs + v_cs)
    tall, flat = split_vowel(v_cs, ub[3] - ub[1])
    cls = H.vowel_class(v)
    if cls in (0, 2) and not tall:
        return False
    if cls in (1, 2) and not flat:
        return False
    if cls == 1 and tall:
        return False
    ib = box(i_cs)
    if tall and ib[2] > min(M.bounds(q)[0] for q in tall) + 10:
        return False
    # the initial ends above the flat vowel's bar (a ㅗ tick may rise between its legs)
    if flat and cls != 0 and ib[1] < box(flat)[1] + 60:
        return False
    return True


def compose(glyph_set, cmap, weight):
    drawn, parts = capture(glyph_set, cmap, weight)
    vow = collections.defaultdict(list)
    ini = collections.defaultdict(list)
    fin = collections.defaultdict(list)
    for cp, (i_cs, v_cs, f_cs) in parts.items():
        i, v, f = H.decompose(cp)
        hf = bool(f)
        # a double initial splits badly (its second half is taken for the vowel): its
        # syllables lend only their final
        if i not in H.DOUBLE_OF and sound(i_cs, v_cs, v):
            vow[(v, hf)].append((cp, v_cs))
            ini[(i, v, hf)].append((cp, i_cs))
        if f and f_cs:
            fin[(f, v)].append((cp, f_cs))
    V = {k: medoid(x)[1] for k, x in vow.items()}
    I = {k: medoid(x)[1] for k, x in ini.items()}
    F = {k: medoid(x)[1] for k, x in fin.items()}
    stats = collections.Counter()

    def near_vowels(v):
        cls = H.vowel_class(v)
        return sorted((w for w in range(21) if H.vowel_class(w) == cls and w != v), key=lambda w: abs(w - v))

    def vowel_part(v, hf):
        if (v, hf) in V:
            return V[(v, hf)]
        if (v, not hf) in V:
            stats["vowel from the other final state"] += 1
            return V[(v, not hf)]
        raise SystemExit(f"no vowel part for {v}")

    def initial_part(i, v, hf):
        if (i, v, hf) in I:
            return I[(i, v, hf)]
        for w in near_vowels(v):
            if (i, w, hf) in I:
                stats["initial borrowed from a nearby vowel"] += 1
                return I[(i, w, hf)]
        single = H.DOUBLE_OF.get(i)
        if single is not None:
            base = initial_part(single, v, hf)
            if base is not None:
                # two copies side by side, each 0.55 as wide, in the single's box
                b = box(base)
                w = b[2] - b[0]
                left = M.transformed(H.flatten(base), 0.55, b[0] * 0.45, 1.0, 0.0)
                right = M.transformed(H.flatten(base), 0.55, b[0] * 0.45 + w * 0.55 + 15, 1.0, 0.0)
                stats["double built from the single"] += 1
                return M.polygon_points_ops(weight(left + right, 68 * 0.45, 0.0))
        if (i, v, not hf) in I:
            stats["initial from the other final state"] += 1
            return I[(i, v, not hf)]
        for w in near_vowels(v):
            if (i, w, not hf) in I:
                stats["initial from a nearby vowel, other final state"] += 1
                return I[(i, w, not hf)]
        return None

    def final_part(f, v):
        if (f, v) in F:
            return F[(f, v)]
        # the final from another vowel, set where finals stand under this one
        here = [box(cs) for (ff, vv), cs in F.items() if vv == v]
        for w in near_vowels(v) + [x for x in range(21) if H.vowel_class(x) != H.vowel_class(v)]:
            if (f, w) in F:
                cs = F[(f, w)]
                b = box(cs)
                if here:
                    top = sorted(h[3] for h in here)[len(here) // 2]
                    mid = sorted((h[0] + h[2]) / 2 for h in here)[len(here) // 2]
                    cs = H.shift(cs, mid - (b[0] + b[2]) / 2, top - b[3])
                stats["final borrowed from another vowel"] += 1
                return cs
        return None

    def fit_initial(init, vowel, v):
        """Narrow (or press) the initial so it keeps clear of the vowel; keep its left and top."""
        cls = H.vowel_class(v)
        ub = box(init + vowel)
        tall, flat = split_vowel(vowel, ub[3] - ub[1])
        if cls == 1:
            tall, flat = [], vowel
        out = H.flatten(init)
        b = M.bounds(out)
        if cls in (0, 2) and tall:
            limit = min(M.bounds(q)[0] for q in tall) - GAP_SIDE
            if b[2] > limit and limit > b[0] + 50:
                kx = (limit - b[0]) / (b[2] - b[0])
                out = weight(M.transformed(out, kx, b[0] * (1 - kx), 1.0, 0.0), 68 * (1 - kx), 0.0)
                stats["initial narrowed"] += 1
        b = M.bounds(out)
        if cls in (1, 2) and flat:
            fb = box(flat)
            floor = fb[3] + GAP_ABOVE
            if b[1] < floor and b[3] > floor + 50:
                ky = (b[3] - floor) / (b[3] - b[1])
                out = weight(M.transformed(out, 1.0, 0.0, ky, b[3] * (1 - ky)), 0.0, 68 * (1 - ky))
                stats["initial pressed"] += 1
        return M.polygon_points_ops(out)

    uppers = {}
    for i in range(19):
        for v in range(21):
            for hf in (False, True):
                init = initial_part(i, v, hf)
                if init is None:
                    continue
                vowel = vowel_part(v, hf)
                uppers[(i, v, hf)] = fit_initial(init, vowel, v) + vowel
    # how far each final must move down, the same for every initial over its vowel
    drop = {}
    for f in range(1, 28):
        for v in range(21):
            fp = final_part(f, v)
            if fp is None:
                continue
            need = 0.0
            for i in range(19):
                up = uppers.get((i, v, True))
                if up is None:
                    continue
                need = max(need, CLEAR - H.gap_below(up, H.flatten(fp)))
            drop[(f, v)] = need
    out = {}
    for cp in range(H.BASE, H.BASE + 11172):
        if cp not in cmap:
            continue
        i, v, f = H.decompose(cp)
        up = uppers.get((i, v, bool(f)))
        if up is None:
            stats["left out: no upper part"] += 1
            continue
        if not f:
            out[cmap[cp]] = H.flatten(up)
            stats["open"] += 1
            continue
        fp = final_part(f, v)
        if fp is None:
            stats["left out: no final"] += 1
            continue
        d = drop[(f, v)]
        placed = H.flatten(fp)
        if d > 0:
            placed = M.transformed(placed, 1.0, 0.0, 1.0, -d)
            pb = M.bounds(placed)
            if pb[1] < -230:
                ky = (pb[3] + 230) / (pb[3] - pb[1])
                placed = weight(M.transformed(placed, 1.0, 0.0, ky, pb[3] * (1 - ky)), 0.0, 68 * (1 - ky))
        out[cmap[cp]] = H.flatten(up) + placed
        stats["with a final"] += 1
    helpers = {"initial": initial_part, "vowel": vowel_part, "final": final_part, "fit": fit_initial,
               "drop": drop, "uppers": uppers}
    return out, stats, {"V": len(V), "I": len(I), "F": len(F), "trusted": len(parts), "drawn": len(drawn)}, helpers

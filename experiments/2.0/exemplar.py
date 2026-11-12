"""Modern Hangul composed from the designer's own jamo instead of averaged frames.

For every jamo slot (initial, vowel, final) of a syllable, the frame comes from a drawn
syllable that has the same jamo there, in the closest context: the same vowel and
final-or-not first (the same initial for a vowel, the same vowel for a final), then the
same vowel class; among those, the one whose box is nearest the slot's box. Its frame
(points, rings, bends, in its own box) is set into the slot's box, which comes from the
learned medians as before. A drawn syllable keeps its own fit whole.

parts_for(cp) -> [(frame, box)], with ROLE per part; boxes in source units."""
import pickle, collections
import numpy as np
import frames as FR, hangul_fill as H

I = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"; V = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
F = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"


def names_of(cp):
    i, v, f = H.decompose(cp)
    return [I[i], V[v]] + ([F[f]] if f else [])


def samples(fr, b, n=12):
    """Centreline points of a frame set in box b (as the drawing places them)."""
    g = FR.in_box(fr, b)
    bs = fr.get("b", [0] * len(g["s"]))
    size = max(b[2] - b[0] - FR.PEN, b[3] - b[1] - FR.PEN)
    pts = [np.asarray(FR.curve(g["p"][i], g["p"][j], bs[k] * size if k < len(bs) else 0, n=n)) for k, (i, j) in enumerate(g["s"])]
    for cx, cy, rx, ry in g["r"]:
        a = np.linspace(0, 2 * np.pi, 24)
        pts.append(np.column_stack([cx + abs(rx) * np.cos(a), cy + abs(ry) * np.sin(a)]))
    return np.vstack(pts) if pts else np.zeros((0, 2))


def shortfall(combo, least):
    """How far the closest two jamo of a combination fall short of their least white."""
    S = [samples(fr, b) for fr, b, _ in combo]
    worst = 0.0
    for x in range(len(S)):
        for y in range(x + 1, len(S)):
            key = "".join(sorted({combo[x][2], combo[y][2]}, key="IVF".index))
            if not len(S[x]) or not len(S[y]) or key not in least:
                continue
            d = np.hypot(S[x][:, None, 0] - S[y][None, :, 0], S[x][:, None, 1] - S[y][None, :, 1]).min() - FR.PEN
            worst = max(worst, least[key] - d)
    return worst


def worst_pair(combo, least):
    S = [samples(fr, b) for fr, b, _ in combo]
    worst, pair = 0.0, None
    for x in range(len(S)):
        for y in range(x + 1, len(S)):
            key = "".join(sorted({combo[x][2], combo[y][2]}, key="IVF".index))
            if not len(S[x]) or not len(S[y]) or key not in least:
                continue
            d = np.hypot(S[x][:, None, 0] - S[y][None, :, 0], S[x][:, None, 1] - S[y][None, :, 1]).min() - FR.PEN
            if least[key] - d > worst:
                worst, pair = least[key] - d, (x, y)
    return worst, pair


def relieve(combo, least, step=0.03, most=0.15):
    """Two jamo that come too close are made smaller about their middles, 3% at a time
    (at most 15%), until they keep the least white: the designer, too, writes jamo
    smaller in a crowded syllable."""
    combo = list(combo)
    shrunk = [0.0] * len(combo)
    for _ in range(int(most / step) * 2):
        worst, pair = worst_pair(combo, least)
        if pair is None:
            break
        moved = False
        for x in pair:
            if shrunk[x] < most - 1e-9:
                fr, b, role = combo[x]
                cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
                k = 1 - step
                combo[x] = (fr, (cx + (b[0] - cx) * k, cy + (b[1] - cy) * k, cx + (b[2] - cx) * k, cy + (b[3] - cy) * k), role)
                shrunk[x] += step; moved = True
        if not moved:
            break
    return combo


class Exemplars:
    def __init__(self, fits, drawn, box):
        """fits: cp -> fit; drawn: the designer's syllables; box(*keys): learned medians."""
        self.fits, self.box = fits, box
        self.units = collections.defaultdict(list)       # (role, jamo) -> [(cp, box, frame)]
        self.own = {}
        whites = collections.defaultdict(list)
        for cp in drawn:
            r = fits.get(cp)
            if not r or not FR.good(r) or FR.twisted(r, names_of(cp)):
                continue
            ub = FR.unit_boxes(r)
            self.own[cp] = ub
            i, v, f = H.decompose(cp)
            jam = [i, v, f]
            for n, b, fr in ub:
                self.units[(n, jam[n])].append((cp, b, fr))
            S = [samples(fr, b) for _, b, fr in ub]
            for x in range(len(S)):
                for y in range(x + 1, len(S)):
                    d = np.hypot(S[x][:, None, 0] - S[y][None, :, 0], S[x][:, None, 1] - S[y][None, :, 1]).min() - FR.PEN
                    whites["IVF"[ub[x][0]] + "IVF"[ub[y][0]]].append(d)
        # the designer's least white between two jamo: 1st percentile of the drawn
        self.least = {k: float(np.percentile(v, 1)) for k, v in whites.items()}

    def ranked(self, role, jamo, cp, slot_box, n=4):
        """The n best candidates for a slot, best first."""
        i, v, f = H.decompose(cp)
        hf = bool(f); vc = H.vowel_class(v)
        cands = self.units.get((role, jamo), [])

        def ctx(c):
            ci, cv, cf = H.decompose(c)
            same_v, same_hf = cv == v, bool(cf) == hf
            near = {0: same_v and same_hf, 1: ci == i and same_hf, 2: same_v}[role]
            close = {0: H.vowel_class(cv) == vc and same_hf, 1: same_hf, 2: H.vowel_class(cv) == vc}[role]
            return 0 if near else 1 if close else 2
        return [e[2] for e in sorted(cands, key=lambda e: (ctx(e[0]), sum(abs(a - b) for a, b in zip(e[1], slot_box))))[:n]]

    def pick(self, role, jamo, cp, slot_box):
        i, v, f = H.decompose(cp)
        hf = bool(f); vc = H.vowel_class(v)
        cands = self.units.get((role, jamo), [])
        if not cands:
            return None

        def ctx(c):
            ci, cv, cf = H.decompose(c)
            same_v, same_hf = cv == v, bool(cf) == hf
            near = {0: same_v and same_hf, 1: ci == i and same_hf, 2: same_v}[role]
            close = {0: H.vowel_class(cv) == vc and same_hf, 1: same_hf, 2: H.vowel_class(cv) == vc}[role]
            return 0 if near else 1 if close else 2
        best = min(cands, key=lambda e: (ctx(e[0]), sum(abs(a - b) for a, b in zip(e[1], slot_box))))
        return best[2]

    def parts_for(self, cp):
        """[(frame, box, role)] for syllable cp."""
        if cp in self.own:
            return [(fr, b, "IVF"[n]) for n, b, fr in self.own[cp]]
        i, v, f = H.decompose(cp); hf = bool(f); vc = H.vowel_class(v)
        single = H.DOUBLE_OF.get(i, i)
        slots = [(0, i, self.box(("I", i, v, hf), ("I", i, vc, hf), ("I", single, v, hf), ("I*", vc, hf))),
                 (1, v, self.box(("V", v, hf, "I", i), ("V", v, hf, i in H.DOUBLE_OF), ("V", v, hf), ("V", v, not hf)))]
        if f:
            slots.append((2, f, self.box(("F", f, v, "I", i), ("F", f, v), ("F", f, vc), ("F*", vc))))
        options = []
        for role, jamo, b in slots:
            c = self.ranked(role, jamo, cp, b) or [FR.FRAMES[[I, V, F][role][jamo]]]
            options.append([(fr, b, "IVF"[role]) for fr in c])
        # the closest combination whose jamo keep the designer's least white apart
        import itertools
        best, best_key = None, None
        for k, combo in enumerate(itertools.product(*options)):
            short = shortfall(combo, self.least)
            rank = sum(combo_idx for combo_idx in np.unravel_index(k, [len(o) for o in options]))
            key = (short > 0, short, rank)
            if best_key is None or key < best_key:
                best, best_key = list(combo), key
            if short <= 0 and rank == 0:
                break
        if best_key[1] > 0:
            best = relieve(best, self.least)
        return best
